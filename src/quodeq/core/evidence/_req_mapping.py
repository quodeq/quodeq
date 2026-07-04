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
    req_to_principle = (
        _resolve_req_to_principle_map(dimension, evaluators_dir, compiled_dir)
        if dimension else {}
    )
    canonical = {p for p in req_to_principle.values() if p}
    sc_violations: dict[str, list[Judgment]] = {}
    sc_compliance: dict[str, list[Judgment]] = {}
    sc_severity: dict[str, str] = {}

    for j in judgments:
        principle = req_to_principle.get(j.practice_id, j.practice_id)
        # When the dimension has a standard, a finding whose principle is not
        # one the standard defines is unmappable: quarantine it (keep it out of
        # principle scoring) and log, so a misfiled finding -- a critical, in the
        # worst case -- is never silently turned into a phantom principle (e.g.
        # an "N/A" card on the dashboard). Without a standard (canonical empty),
        # stay permissive and group by the raw principle.
        if canonical and principle not in canonical:
            _logger.warning(
                "Quarantining unmapped %s finding in dimension %r: principle %r "
                "not in standard (practice_id=%r, req=%r, file=%s)",
                j.severity or "?", dimension, principle, j.practice_id, j.req, j.file,
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
