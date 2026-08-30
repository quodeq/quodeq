"""Requirement-to-principle mapping helpers for evidence grouping."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.core.events.models import Judgment

_SEV_RANKS = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Reads ``<directory>/<dimension>.json`` into a req-id → principle-name map.
# Injected by outer layers (see quodeq.data.fs.standards_loader.
# read_req_to_principle_map); core itself never touches the filesystem.
ReqMapReader = Callable[[Path, str], "dict[str, str] | None"]


def _sev_rank(sev: str) -> int:
    return _SEV_RANKS.get(sev, 1)


@dataclass(frozen=True)
class QuarantinedFinding:
    """One finding dropped for naming a principle the standard does not
    define -- the per-finding detail behind the ``quarantined`` counter,
    handed to an ``on_quarantine`` sink instead of logged in core."""
    dimension: str
    practice_id: str | None
    principle: str | None
    req: str | None
    file: str
    severity: str


QuarantineSink = Callable[[list[QuarantinedFinding]], None]


@dataclass
class _GroupedJudgments:
    violations: dict[str, list[Judgment]]
    compliance: dict[str, list[Judgment]]
    severity: dict[str, str]
    # Findings dropped for naming a principle the standard does not define.
    # Reported as run metadata so a run that discarded most of its evidence is
    # distinguishable from a clean one; never re-joined to the findings lists.
    quarantined: int = 0
    # Per-finding detail behind `quarantined`. Appended once per dropped
    # judgment, in the same loop, with no dedup/set/filter -- so
    # len(quarantined_findings) == quarantined always (see invariant test).
    quarantined_findings: list[QuarantinedFinding] = field(default_factory=list)


def _resolve_req_to_principle_map(
    dimension: str,
    evaluators_dir: Path | None = None,
    compiled_dir: Path | None = None,
    req_map_reader: ReqMapReader | None = None,
) -> dict[str, str]:
    """Resolve the requirement-to-principle map for *dimension*.

    A custom evaluator standard (evaluators_dir) is authoritative when it
    defines the dimension; otherwise fall back to the compiled built-in
    standard (compiled_dir). On real installs the evaluators dir exists but
    is empty for built-in dimensions, so without the fallback the map is
    empty and standard-validation callers silently go permissive.

    The directories are only ever handed to *req_map_reader*; core performs
    no file I/O itself, so without a reader the map is empty (permissive).
    """
    if req_map_reader is None:
        return {}
    mapping = req_map_reader(evaluators_dir, dimension) if evaluators_dir is not None else None
    if not mapping and compiled_dir is not None:
        mapping = req_map_reader(compiled_dir, dimension)
    return mapping or {}


def _id_shape(req_id: str) -> tuple[str, str] | None:
    """The trailing ``(category, number)`` of a requirement ID, upper-cased.

    ``CLEA-DEP-05`` and ``DEP-05`` both shape to ``("DEP", "05")``. Returns
    None for anything without at least two dash-separated segments ending in
    a number, which is the only form we are willing to guess about.
    """
    parts = [p for p in (req_id or "").strip().split("-") if p]
    if len(parts) < 2 or not parts[-1].isdigit():
        return None
    return parts[-2].upper(), parts[-1].lstrip("0") or "0"


def normalize_req_id(raw: str, canonical_ids) -> str | None:
    """Fold a near-miss requirement ID onto the standard's real ID.

    Local models emit IDs the standard does not define -- wrong case
    (``CLEa-DEP-05``), a truncated prefix (``CLE-TES-02``) or no prefix at all
    (``SEP-03``). Each is a real finding that would otherwise be quarantined
    over a typo.

    The match is on the trailing ``(category, number)`` pair, so two genuinely
    different requirements can never merge: ``CLEA-DEP-01`` and ``CLEA-DEP-02``
    differ in the number and stay distinct despite being one character apart.
    An ambiguous shape (two canonical IDs sharing the pair) refuses to fold --
    guessing between real requirements is worse than quarantining.
    """
    ids = tuple(canonical_ids or ())
    if not raw or not ids:
        return None
    for candidate in ids:
        if candidate == raw:
            return candidate
    shape = _id_shape(raw)
    if shape is None:
        return None
    matches = [c for c in ids if _id_shape(c) == shape]
    if len(matches) != 1:
        return None  # unknown, or ambiguous between real requirements
    return matches[0]


@dataclass(frozen=True)
class PrincipleResolver:
    """Resolves a finding's raw principle/requirement ID to a canonical principle.

    The single source of truth for "does this finding belong to the dimension's
    standard?". Both the report path (:func:`_group_judgments`) and the live
    scan counters resolve through this, so the counters the UI shows mid-scan
    and the persisted evaluation JSON can never disagree on which findings count.
    """

    req_to_principle: dict[str, str]
    canonical: frozenset[str]

    def resolve(self, practice_id: str | None) -> str | None:
        """Canonical principle name, or None when the finding is unmappable.

        None means quarantine: the dimension has a standard and this finding's
        principle is not one it defines. With no standard (canonical empty) every
        finding maps through unchanged, keeping callers permissive. A missing
        practice_id never resolves — it has no principle to group under.
        """
        if not practice_id:
            return None
        principle = self.req_to_principle.get(practice_id)
        if principle is None:
            # Second chance before quarantine: fold a near-miss ID (wrong case,
            # truncated or missing prefix) onto the standard's real one.
            folded = normalize_req_id(practice_id, tuple(self.req_to_principle))
            if folded is not None:
                principle = self.req_to_principle[folded]
        if principle is None:
            # Not a requirement ID: findings may name the principle directly,
            # and with no standard at all every id passes through unchanged.
            principle = practice_id
        if self.canonical and principle not in self.canonical:
            return None
        return principle


def build_principle_resolver(
    dimension: str, evaluators_dir: Path | None = None,
    compiled_dir: Path | None = None,
    *, req_map_reader: ReqMapReader | None = None,
) -> PrincipleResolver:
    """Build the resolver for *dimension* from its standard.

    A custom evaluator standard wins; otherwise the compiled built-in standard.
    An unknown/blank dimension yields a permissive resolver. The directories and
    *req_map_reader* must be supplied by the caller; the core layer does not
    resolve paths or read files itself.
    """
    mapping = (
        _resolve_req_to_principle_map(dimension, evaluators_dir, compiled_dir,
                                      req_map_reader)
        if dimension else {}
    )
    return PrincipleResolver(mapping, frozenset(p for p in mapping.values() if p))


def principle_names_for_dimension(
    dimension: str, evaluators_dir: Path | None = None,
    compiled_dir: Path | None = None,
    *, req_map_reader: ReqMapReader | None = None,
) -> set[str]:
    """Return the principle names defined by *dimension*'s standard.

    Empty when no standard is available from either source, so callers stay
    permissive (no standard to validate against) rather than dropping
    everything. The directories and *req_map_reader* must be supplied by the
    caller; the core layer does not resolve paths or read files itself.
    """
    mapping = _resolve_req_to_principle_map(dimension, evaluators_dir, compiled_dir,
                                            req_map_reader)
    return {p for p in mapping.values() if p}


def _group_judgments(
    judgments: list[Judgment],
    dimension: str = "",
    evaluators_dir: Path | None = None,
    compiled_dir: Path | None = None,
    *, req_map_reader: ReqMapReader | None = None,
) -> _GroupedJudgments:
    resolver = build_principle_resolver(dimension, evaluators_dir, compiled_dir,
                                        req_map_reader=req_map_reader)
    sc_violations: dict[str, list[Judgment]] = {}
    sc_compliance: dict[str, list[Judgment]] = {}
    sc_severity: dict[str, str] = {}
    quarantined = 0
    quarantined_findings: list[QuarantinedFinding] = []

    for j in judgments:
        # When the dimension has a standard, a finding whose principle is not
        # one the standard defines is unmappable: quarantine it (keep it out of
        # principle scoring) and record it, so a misfiled finding -- a critical,
        # in the worst case -- is never silently turned into a phantom principle
        # (e.g. an "N/A" card on the dashboard). Logging happens in the outer
        # layer via the caller's `on_quarantine` sink; core only collects the
        # data. The live scan counters resolve through the same
        # PrincipleResolver, so they exclude exactly these findings too.
        principle = resolver.resolve(j.practice_id)
        if principle is None:
            quarantined_findings.append(QuarantinedFinding(
                dimension=dimension,
                practice_id=j.practice_id,
                principle=resolver.req_to_principle.get(j.practice_id, j.practice_id),
                req=j.req,
                file=j.file,
                severity=j.severity or "?",
            ))
            quarantined += 1
            continue
        if j.verdict == "violation":
            sc_violations.setdefault(principle, []).append(j)
        elif j.verdict == "compliance":
            sc_compliance.setdefault(principle, []).append(j)
        sev = j.severity or "medium"
        if principle not in sc_severity or _sev_rank(sev) > _sev_rank(sc_severity[principle]):
            sc_severity[principle] = sev

    return _GroupedJudgments(sc_violations, sc_compliance, sc_severity, quarantined,
                              quarantined_findings)
