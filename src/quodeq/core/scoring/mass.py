# src/quodeq/core/scoring/mass.py
"""Per-requirement mass: the unit the grade is built from.

One row per broken requirement, weighted by how many of the project's files it
touches. Severity is cumulative over per-file worst severities, so a rule that
is minor in 100 files and major in 20 adds the spread of 120 files at the minor
weight plus the spread of 20 files at the major increment. The severity of a
finding is the one it carries: the model's rating, as gated at scan time. The
standard's suggested severity is shown to the model, never applied here.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.severity import Severity, parse_severity

SPREAD_PER_FILES = 100     # density is "files hit per 100 project files"
DENOMINATOR_FLOOR = 100    # a 6-file project is not destroyed by one finding
_KEY_FIELDS = ("req", "vt", "reason")
_UNKNOWN_KEY = "unknown"
_NO_FILE = ""
LADDER: tuple[str, ...] = (Severity.MINOR, Severity.MAJOR, Severity.CRITICAL)
_RANK = {sev: i for i, sev in enumerate(LADDER)}


def spread(files_hit: int, project_files: int) -> float:
    """``1 + log2(1 + 100 · n / files)`` for n ≥ 1, 0 for n = 0; 1 when the size is unknown."""
    if files_hit <= 0:
        return 0.0
    if project_files <= 0:
        return 1.0
    denominator = max(project_files, DENOMINATOR_FLOOR)
    return 1.0 + math.log2(1.0 + SPREAD_PER_FILES * files_hit / denominator)


def finding_key(item: Mapping) -> str:
    """The rule a finding is filed under: ``req``, else ``vt``, else ``reason``."""
    return next((str(item[k]) for k in _KEY_FIELDS if item.get(k)), _UNKNOWN_KEY)


@dataclass(frozen=True, slots=True)
class RequirementRows:
    """Violations as ``{req: {file: worst model severity}}``, compliance and dismissed as ``{req: files}``.

    Dismissed files carry no penalty but stay observed: a dismissal raises its
    principle and never shrinks the principle's weight in the dimension.
    """

    violations: Mapping[str, Mapping[str, str]]
    compliance: Mapping[str, frozenset[str]]
    dismissed: Mapping[str, frozenset[str]] = field(default_factory=dict)


def _files_by_rule(items: Iterable[Mapping]) -> dict[str, frozenset[str]]:
    by_rule: dict[str, set[str]] = {}
    for item in items:
        by_rule.setdefault(finding_key(item), set()).add(str(item.get("file") or _NO_FILE))
    return {req: frozenset(files) for req, files in by_rule.items()}


def requirement_rows(
    violations: Iterable[Mapping], compliance: Iterable[Mapping], dismissed: Iterable[Mapping] = (),
) -> RequirementRows:
    """Group findings per rule and file; repeats in one file collapse to the worst."""
    worst: dict[str, dict[str, str]] = {}
    for item in violations:
        sev = parse_severity(item.get("severity"))
        files = worst.setdefault(finding_key(item), {})
        file = str(item.get("file") or _NO_FILE)
        if file not in files or _RANK[sev] > _RANK[files[file]]:
            files[file] = sev
    return RequirementRows(
        violations={req: dict(files) for req, files in worst.items()},
        compliance=_files_by_rule(compliance),
        dismissed=_files_by_rule(dismissed),
    )


@dataclass(frozen=True, slots=True)
class ViolationRow:
    """One broken requirement: files reached at each severity level and the resulting weight."""

    req: str
    files_at_least: Mapping[str, int]
    spread_at_least: Mapping[str, float]
    weight: float
    worst: str


@dataclass(frozen=True, slots=True)
class ComplianceRow:
    """One requirement the code satisfies, with the spread of the files that satisfy it."""

    req: str
    files_ok: int
    spread: float


@dataclass(frozen=True, slots=True)
class PrincipleMass:
    """The summed rows of one principle, ready for the grade formula."""

    violation_mass: float
    compliance_mass: float
    observation: float
    worst: str | None
    violations: tuple[ViolationRow, ...]
    compliance: tuple[ComplianceRow, ...]


def _increments(params: ScoringParams) -> dict[str, float]:
    """Weight added at each level: minor, then major minus minor, then critical minus major."""
    w = params.severity_weight
    incs = {
        Severity.MINOR: float(w[Severity.MINOR]),
        Severity.MAJOR: float(w[Severity.MAJOR]) - float(w[Severity.MINOR]),
        Severity.CRITICAL: float(w[Severity.CRITICAL]) - float(w[Severity.MAJOR]),
    }
    if any(v <= 0 for v in incs.values()):
        raise ValueError("severity weights must be strictly increasing on the ladder")
    return incs


def requirement_mass(
    file_severities: Mapping[str, str], project_files: int,
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> ViolationRow:
    """Cumulative mass of one rule from its per-file worst severities."""
    incs = _increments(params)
    files_at_least = {lvl: sum(1 for s in file_severities.values() if _RANK[s] >= _RANK[lvl]) for lvl in LADDER}
    spread_at_least = {lvl: spread(n, project_files) for lvl, n in files_at_least.items()}
    weight = sum(incs[lvl] * spread_at_least[lvl] for lvl in LADDER)
    worst = max(file_severities.values(), key=lambda s: _RANK[s], default=Severity.MINOR)
    return ViolationRow(
        req="", files_at_least=files_at_least, spread_at_least=spread_at_least, weight=weight, worst=worst,
    )


def principle_mass(
    rows: RequirementRows, project_files: int,
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> PrincipleMass:
    """Sum the rule masses of a principle; observation is the spread of every observed rule.

    A rule's observed files are its violating files plus its dismissed ones.
    """
    violations: list[ViolationRow] = []
    worst: str | None = None
    for req in sorted(rows.violations):
        row = requirement_mass(rows.violations[req], project_files, params=params)
        violations.append(replace(row, req=req))
        if worst is None or _RANK[row.worst] > _RANK[worst]:
            worst = row.worst
    compliance = tuple(
        ComplianceRow(req=req, files_ok=len(files), spread=spread(len(files), project_files))
        for req, files in sorted(rows.compliance.items())
    )
    observed: dict[str, set[str]] = {req: set(files) for req, files in rows.violations.items()}
    for req, files in rows.dismissed.items():
        observed.setdefault(req, set()).update(files)
    observation = sum(spread(len(files), project_files) for files in observed.values())
    observation += sum(c.spread for c in compliance)
    return PrincipleMass(
        violation_mass=sum(r.weight for r in violations),
        compliance_mass=sum(c.spread for c in compliance),
        observation=observation,
        worst=worst,
        violations=tuple(violations),
        compliance=compliance,
    )
