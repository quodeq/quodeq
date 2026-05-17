"""Requirement-to-principle mapping helpers for evidence grouping."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from quodeq.core.events.models import Judgment

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
        data = json.loads(path.read_text())
        mapping: dict[str, str] = {}
        for principle in data.get("principles", []):
            pname = principle.get("name", "")
            for req in principle.get("requirements", []):
                rid = req.get("id", "")
                if rid and pname:
                    mapping[rid] = pname
        return mapping
    except (OSError, ValueError):
        return {}


def _group_judgments(
    judgments: list[Judgment],
    dimension: str = "",
    evaluators_dir: Path | None = None,
) -> _GroupedJudgments:
    req_to_principle = _build_req_to_principle_map(dimension, evaluators_dir) if dimension else {}
    sc_violations: dict[str, list[Judgment]] = {}
    sc_compliance: dict[str, list[Judgment]] = {}
    sc_severity: dict[str, str] = {}

    for j in judgments:
        principle = req_to_principle.get(j.practice_id, j.practice_id)
        if j.verdict == "violation":
            sc_violations.setdefault(principle, []).append(j)
        elif j.verdict == "compliance":
            sc_compliance.setdefault(principle, []).append(j)
        sev = j.severity or "medium"
        if principle not in sc_severity or _sev_rank(sev) > _sev_rank(sc_severity[principle]):
            sc_severity[principle] = sev

    return _GroupedJudgments(sc_violations, sc_compliance, sc_severity)
