"""Run a dimension's deterministic checkers and fold the results into its evidence.

Every step here is fail-soft. A checker that raises, a standard that will not
load, a JSONL that will not open -- each costs the deterministic findings and
nothing else. The LLM's findings, the score and the run itself carry on. A
check that can take a run down is worse than a check that does not exist.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Sequence
from pathlib import Path

from quodeq.analysis.checks.registry import CHECKERS, CheckContext
from quodeq.analysis.mcp.provenance_gate import DOWNGRADE_MARKER
from quodeq.analysis.mcp.scope_gate import SCOPE_DOWNGRADE_MARKER
from quodeq.analysis.mcp.severity_gates import apply_severity_gates
from quodeq.context.trust_model import TrustModel, resolve_trust_model
from quodeq.core.events.models import Judgment, JudgmentCreatedEvent
from quodeq.core.evidence._jsonl import judgment_to_dict
from quodeq.core.evidence._req_mapping import build_principle_resolver
from quodeq.core.evidence.model import Evidence, PrincipleEvidence
from quodeq.data.fs.standards_loader import load_requirement_checks

_logger = logging.getLogger(__name__)


def deterministic_judgments(
    *,
    root: Path,
    source_files: Sequence[str],
    dimension: str,
    compiled_dir: Path | None,
    evaluators_dir: Path | None = None,
) -> list[Judgment]:
    """Judgments from every checker *dimension*'s standard asks for.

    Each named checker runs once regardless of how many requirements name it,
    and its judgments are filtered back to those requirements -- a standard
    that declares the checker on only one of the two requirements it can
    answer gets findings for that one only.
    """
    if not source_files:
        return []
    try:
        declared = load_requirement_checks(compiled_dir, dimension, evaluators_dir)
    except Exception:  # a broken standard must not stop the run
        _logger.warning("checks: could not read %s's standard", dimension, exc_info=True)
        return []
    if not declared:
        return []

    context = CheckContext(root=Path(root), source_files=tuple(source_files),
                           dimension=dimension)
    out: list[Judgment] = []
    for name in sorted(declared):
        checker = CHECKERS.get(name)
        if checker is None:
            # A standard naming a checker this build does not have. Standards
            # ship as data and outlive binaries; skip it and keep the rest.
            _logger.info("checks: %r is not a checker this build knows", name)
            continue
        try:
            produced = checker(context)
        except Exception:  # one bad checker must not lose the others
            _logger.warning("checks: %r failed on %s", name, root, exc_info=True)
            continue
        wanted = declared[name]
        out.extend(j for j in produced if j.practice_id in wanted)
    return out


def _to_wire(j: Judgment) -> dict:
    """Serialize a Judgment into the short-key JSONL row an LLM would have written.

    Symmetric with ``core/evidence/_jsonl.parse_jsonl_line`` so a deterministic
    finding re-reads exactly like any other: p=practice_id, t=verdict,
    d=dimension, w=title, vt=violation_type.
    """
    row = {
        "p": j.practice_id, "t": j.verdict, "d": j.dimension,
        "file": j.file, "line": j.line, "severity": j.severity,
        "reason": j.reason, "confidence": j.confidence,
    }
    for key, value in (("req", j.req), ("w", j.title), ("snippet", j.snippet),
                       ("end_line", j.end_line), ("context", j.context),
                       ("scope", j.scope), ("vt", j.violation_type)):
        if value:
            row[key] = value
    return row


def _merge_into_evidence(evidence: Evidence, judgments: list[Judgment],
                         resolver) -> int:
    """Add *judgments* to their principles, recomputing metrics. Returns the count.

    A checker reports both verdicts: a violation when it found something and a
    compliance when it ran clean. Routing on ``j.verdict`` rather than assuming
    violations is what keeps a clean check from scoring as a defect.
    """
    added = 0
    for j in judgments:
        principle = resolver.resolve(j.practice_id)
        if principle is None:
            _logger.warning(
                "checks: dropping %s — %r is not a principle of %r",
                j.file, j.practice_id, j.dimension,
            )
            continue
        pe = evidence.principles.get(principle)
        if pe is None:
            pe = PrincipleEvidence(
                practice_id=principle, display_name=principle,
                dimension=j.dimension, severity=j.severity,
            )
            evidence.principles[principle] = pe
        row = [judgment_to_dict(j)]
        if j.verdict == "compliance":
            pe.add_compliance(row)
        else:
            pe.add_violations(row)
        added += 1
    return added


def _gate(j: Judgment, trust_model: TrustModel | None) -> tuple[Judgment, dict]:
    """Run one judgment through the shared severity gates.

    Returns the judgment at its gated severity and the wire row that produced
    it. Both are updated with whichever markers fired, because they feed two
    different sinks downstream: ``_persist`` writes the row verbatim to the
    per-dim JSONL, and mirrors the judgment (not the row) into events.jsonl,
    which is what the SQL projection and the dashboard actually read. A
    marker set on the row alone would reach the report file but never the
    live feed, the DB, or the UI.

    ``_to_wire`` is what makes this cheap: it already emits the short-key shape
    (``t``/``req``/``severity``/``reason``/``w``) the gates read at the other
    two sinks, so a checker finding is gated on exactly the evidence an LLM
    finding would be.
    """
    row = _to_wire(j)
    if not apply_severity_gates(row, trust_model):
        return j, row
    update: dict = {"severity": row["severity"]}
    if row.get(DOWNGRADE_MARKER):
        update["provenance_downgrade"] = True
    if row.get(SCOPE_DOWNGRADE_MARKER):
        update["scope_downgrade"] = row[SCOPE_DOWNGRADE_MARKER]
    return dataclasses.replace(j, **update), row


def _persist(jsonl_path: Path, judgments: list[Judgment], rows: list[dict]) -> None:
    """Append to the per-dim JSONL and mirror into the run's event log.

    Both stores, always. The SQL projection runs off ``events.jsonl`` while
    the report path reads the per-dim JSONL; writing only one is how the
    dashboard and the CLI end up disagreeing about the same run.

    *rows* are the gated wire rows from :func:`_gate`, written rather than
    re-derived from *judgments*: ``_to_wire`` never emits the downgrade
    markers, so re-deriving would silently drop them from the per-dim JSONL
    even though both markers now also live on the ``Judgment`` itself for
    the events.jsonl mirror below.
    """
    try:
        with jsonl_path.open("a", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps(row) + "\n")
    except OSError:
        _logger.warning("checks: could not append to %s", jsonl_path, exc_info=True)

    from quodeq.data.events.writer import EventLogWriter

    try:
        writer = EventLogWriter(jsonl_path.parent.parent / "events.jsonl")
        for j in judgments:
            writer.emit(JudgmentCreatedEvent(payload=j))
    except Exception:  # the findings are already in the evidence
        _logger.warning("checks: could not mirror findings to the event log", exc_info=True)


def apply_deterministic_checks(
    evidence: Evidence,
    *,
    root: Path,
    source_files: Sequence[str],
    dimension: str,
    compiled_dir: Path | None,
    jsonl_path: Path | None,
    evaluators_dir: Path | None = None,
    trust_model: TrustModel | None = None,
) -> int:
    """Run *dimension*'s checkers and fold the findings into *evidence*.

    Returns how many findings were added. The evidence is updated before
    anything is written, so a persistence failure costs the run's record of
    these findings but never the score the user is shown for this run.
    """
    judgments = deterministic_judgments(
        root=root, source_files=source_files, dimension=dimension,
        compiled_dir=compiled_dir, evaluators_dir=evaluators_dir,
    )
    if not judgments:
        return 0

    # Gate BEFORE the evidence merge, not just before the write. The evidence
    # is what the score is computed from, so gating only on the way to disk
    # would leave the grade reflecting the ungated severity while the stored
    # finding disagreed with it.
    gated: list[Judgment] = []
    rows: list[dict] = []
    for raw in judgments:
        judgment, row = _gate(raw, trust_model)
        gated.append(judgment)
        rows.append(row)

    resolver = build_principle_resolver(dimension, evaluators_dir, compiled_dir)
    added = _merge_into_evidence(evidence, gated, resolver)
    if added and jsonl_path is not None:
        _persist(jsonl_path, gated, rows)
    return added


def _project_source_files(config) -> list[str]:
    """Every source file in the project, not just this dimension's dispatch list.

    An import graph is only meaningful whole: the outer modules an inner file
    reaches through are exactly the ones a dimension-scoped or incrementally
    filtered list would leave out.
    """
    for holder in (config.target, config.manifest):
        files = getattr(holder, "source_files", None) if holder is not None else None
        if files:
            return list(files)
    return []


def apply_checks_for_run(config, dimension: str, evidence: Evidence) -> int:
    """``apply_deterministic_checks`` adapted to a :class:`RunConfig`.

    Called once per dimension per run. The findings are recomputed every time
    rather than cached: they are properties of the whole import graph, and the
    per-file content cache has no key that could represent "the graph changed".

    Swallows everything. This runs inside a dimension that has already
    succeeded, and no deterministic check is worth failing that.
    """
    try:
        source_files = _project_source_files(config)
        if not source_files:
            return 0
        standards_dir = config.standards_dir
        evidence_dir = config.work_dir or config.src
        # Resolved once per dimension and threaded down, the same way
        # process_dimension_with_cache does it: resolution reads the project
        # profile and walks the manifests, which is per-project work, not
        # per-finding work. Guarding on ``config.src`` rather than assuming it
        # keeps apply_scope_gate's no-op explicit -- resolve_trust_model would
        # degrade to CONSERVATIVE on None, which is a different statement.
        trust_model = resolve_trust_model(config.src) if config.src is not None else None
        return apply_deterministic_checks(
            evidence,
            root=Path(config.src),
            source_files=source_files,
            dimension=dimension,
            compiled_dir=(Path(standards_dir) / "compiled") if standards_dir else None,
            evaluators_dir=config.evaluators_dir,
            jsonl_path=Path(evidence_dir) / f"{dimension}_evidence.jsonl",
            trust_model=trust_model,
        )
    except Exception:  # a check must never fail a dimension that already succeeded
        _logger.warning("checks: skipped for %s", dimension, exc_info=True)
        return 0
