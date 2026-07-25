"""Requirement-to-principle mapping helpers for evidence grouping."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from quodeq.core.events.models import Judgment

_logger = logging.getLogger(__name__)

_SEV_RANKS = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _sev_rank(sev: str) -> int:
    return _SEV_RANKS.get(sev, 1)


@dataclass
class _GroupedJudgments:
    violations: dict[str, list[Judgment]]
    compliance: dict[str, list[Judgment]]
    severity: dict[str, str]


def _build_req_to_principle_map(dimension: str, evaluators_dir: Path | None = None) -> dict[str, str]:
    """Build a mapping from requirement IDs to principle names for custom evaluators.

    Cached per dimension — evaluator files don't change during a single run.
    The *evaluators_dir* must be supplied by the caller (typically from
    RunConfig); the core layer does not resolve paths itself.
    """
    if evaluators_dir is None or not evaluators_dir.is_dir():
        return {}
    path = evaluators_dir / f"{dimension}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        mapping: dict[str, str] = {}
        for principle in data.get("principles", []):
            pname = principle.get("name", "")
            for req in principle.get("requirements", []):
                rid = req.get("id", "")
                if rid and pname:
                    mapping[rid] = pname
        return mapping
    except (OSError, ValueError, AttributeError, TypeError):
        # AttributeError/TypeError: a valid-JSON-but-non-dict payload (a list
        # or null at the top level, or non-dict principle/requirement items)
        # makes .get() raise. The contract is an empty map on any malformed
        # input so callers stay permissive, never a crash.
        return {}


def _resolve_req_to_principle_map(
    dimension: str,
    evaluators_dir: Path | None = None,
    compiled_dir: Path | None = None,
) -> dict[str, str]:
    """Resolve the requirement-to-principle map for *dimension*.

    A custom evaluator standard (evaluators_dir) is authoritative when it
    defines the dimension; otherwise fall back to the compiled built-in
    standard (compiled_dir). On real installs the evaluators dir exists but
    is empty for built-in dimensions, so without the fallback the map is
    empty and standard-validation callers silently go permissive.
    """
    mapping = _build_req_to_principle_map(dimension, evaluators_dir)
    if not mapping:
        mapping = _build_req_to_principle_map(dimension, compiled_dir)
    return mapping


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
        principle = self.req_to_principle.get(practice_id, practice_id)
        if self.canonical and principle not in self.canonical:
            return None
        return principle


def build_principle_resolver(
    dimension: str, evaluators_dir: Path | None = None,
    compiled_dir: Path | None = None,
) -> PrincipleResolver:
    """Build the resolver for *dimension* from its standard.

    A custom evaluator standard wins; otherwise the compiled built-in standard.
    An unknown/blank dimension yields a permissive resolver. The directories must
    be supplied by the caller; the core layer does not resolve paths itself.
    """
    mapping = (
        _resolve_req_to_principle_map(dimension, evaluators_dir, compiled_dir)
        if dimension else {}
    )
    return PrincipleResolver(mapping, frozenset(p for p in mapping.values() if p))


def principle_names_for_dimension(
    dimension: str, evaluators_dir: Path | None = None,
    compiled_dir: Path | None = None,
) -> set[str]:
    """Return the principle names defined by *dimension*'s standard.

    Empty when no standard is available from either source, so callers stay
    permissive (no standard to validate against) rather than dropping
    everything. The directories must be supplied by the caller; the core
    layer does not resolve paths itself.
    """
    mapping = _resolve_req_to_principle_map(dimension, evaluators_dir, compiled_dir)
    return {p for p in mapping.values() if p}


def _group_judgments(
    judgments: list[Judgment],
    dimension: str = "",
    evaluators_dir: Path | None = None,
    compiled_dir: Path | None = None,
) -> _GroupedJudgments:
    resolver = build_principle_resolver(dimension, evaluators_dir, compiled_dir)
    sc_violations: dict[str, list[Judgment]] = {}
    sc_compliance: dict[str, list[Judgment]] = {}
    sc_severity: dict[str, str] = {}

    for j in judgments:
        # When the dimension has a standard, a finding whose principle is not
        # one the standard defines is unmappable: quarantine it (keep it out of
        # principle scoring) and log, so a misfiled finding -- a critical, in the
        # worst case -- is never silently turned into a phantom principle (e.g.
        # an "N/A" card on the dashboard). The live scan counters resolve through
        # the same PrincipleResolver, so they exclude exactly these findings too.
        principle = resolver.resolve(j.practice_id)
        if principle is None:
            _logger.warning(
                "Quarantining unmapped %s finding in dimension %r: principle %r "
                "not in standard (practice_id=%r, req=%r, file=%s)",
                j.severity or "?", dimension,
                resolver.req_to_principle.get(j.practice_id, j.practice_id),
                j.practice_id, j.req, j.file,
            )
            continue
        if j.verdict == "violation":
            sc_violations.setdefault(principle, []).append(j)
        elif j.verdict == "compliance":
            sc_compliance.setdefault(principle, []).append(j)
        sev = j.severity or "medium"
        if principle not in sc_severity or _sev_rank(sev) > _sev_rank(sc_severity[principle]):
            sc_severity[principle] = sev

    return _GroupedJudgments(sc_violations, sc_compliance, sc_severity)
