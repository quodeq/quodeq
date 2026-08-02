"""Run a dimension's deterministic checkers and fold the results into its evidence.

Every step here is fail-soft. A checker that raises, a standard that will not
load, a JSONL that will not open -- each costs the deterministic findings and
nothing else. The LLM's findings, the score and the run itself carry on. A
check that can take a run down is worse than a check that does not exist.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from quodeq.analysis.checks.registry import CHECKERS, CheckContext
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


def _persist(jsonl_path: Path, judgments: list[Judgment]) -> None:
    """Append to the per-dim JSONL and mirror into the run's event log.

    Both stores, always. The SQL projection runs off ``events.jsonl`` while
    the report path reads the per-dim JSONL; writing only one is how the
    dashboard and the CLI end up disagreeing about the same run.
    """
    try:
        with jsonl_path.open("a", encoding="utf-8") as out:
            for j in judgments:
                out.write(json.dumps(_to_wire(j)) + "\n")
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

    resolver = build_principle_resolver(dimension, evaluators_dir, compiled_dir)
    added = _merge_into_evidence(evidence, judgments, resolver)
    if added and jsonl_path is not None:
        _persist(jsonl_path, judgments)
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
        return apply_deterministic_checks(
            evidence,
            root=Path(config.src),
            source_files=source_files,
            dimension=dimension,
            compiled_dir=(Path(standards_dir) / "compiled") if standards_dir else None,
            evaluators_dir=config.evaluators_dir,
            jsonl_path=Path(evidence_dir) / f"{dimension}_evidence.jsonl",
        )
    except Exception:  # a check must never fail a dimension that already succeeded
        _logger.warning("checks: skipped for %s", dimension, exc_info=True)
        return 0
