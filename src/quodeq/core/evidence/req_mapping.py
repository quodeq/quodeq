"""Requirement-to-principle mapping helpers for evidence grouping."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from quodeq.core.admission import Admitted, FindingFacts, StandardCatalog, StandardIndex, admit
from quodeq.core.admission.ids import id_shape, normalize_req_id  # noqa: F401 -- re-exported
from quodeq.core.events.models import DEFAULT_SEVERITY, Judgment

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
class GroupedJudgments:
    """Judgments grouped by principle, plus the findings quarantined on the way."""
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


_RESOLVER_KEY = "_resolver"  # the one dimension a resolver's catalog holds


@dataclass(frozen=True)
class PrincipleResolver:
    """Resolves a finding's requirement (and the principle it named) to a canonical principle.

    The single source of truth for "does this finding belong to the dimension's
    standard?", built on ``core.admission``: every reader places a finding
    with the same rule the writers and the projection use. The report path
    (:func:`group_judgments`), the live counters and the live findings view
    all resolve through this.
    """

    req_to_principle: dict[str, str]
    canonical: frozenset[str]
    _catalog: StandardCatalog = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        index = StandardIndex(_RESOLVER_KEY, self.req_to_principle)
        object.__setattr__(self, "_catalog", StandardCatalog.of([index]))

    def place(self, req: str | None, principle_hint: str | None = None) -> str | None:
        """Canonical principle of a finding with *req* and *principle_hint*, or None.

        None means quarantine: the dimension has a standard and cannot place
        the finding. With no standard (an empty map) the finding keeps the
        principle it named, else its code, keeping callers permissive.
        """
        if not req and not principle_hint:
            return None
        if not self.req_to_principle:
            return principle_hint or req
        facts = FindingFacts(req=req or None, verdict=None, dimension=None, file=None, line=None,
                             principle_hint=principle_hint or None)
        result = admit(facts, self._catalog, _RESOLVER_KEY)
        return result.principle if isinstance(result, Admitted) else None

    def resolve(self, practice_id: str | None) -> str | None:
        """Canonical principle for one id that may be a requirement or a principle name."""
        return self.place(None, practice_id)


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


def group_judgments(
    judgments: list[Judgment],
    dimension: str = "",
    evaluators_dir: Path | None = None,
    compiled_dir: Path | None = None,
    *, req_map_reader: ReqMapReader | None = None,
) -> GroupedJudgments:
    """Group *judgments* into violations, compliance and severity per principle."""
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
        principle = resolver.place(j.req, j.practice_id)
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
        if j.is_violation():
            sc_violations.setdefault(principle, []).append(j)
        elif j.is_compliance():
            sc_compliance.setdefault(principle, []).append(j)
        sev = j.severity or DEFAULT_SEVERITY
        if principle not in sc_severity or _sev_rank(sev) > _sev_rank(sc_severity[principle]):
            sc_severity[principle] = sev

    return GroupedJudgments(sc_violations, sc_compliance, sc_severity, quarantined,
                              quarantined_findings)
