"""Score/grade conversion and score-lookup building for reports."""
from __future__ import annotations

from quodeq.core.types import ScoringResult
from quodeq.shared.serialization import to_camel_dict
from quodeq.core.scoring.report_grades import grade_from_score  # noqa: F401 — re-exported API


def build_score_lookup(per_principle_scores: dict) -> dict:
    """Index per-principle scores by display_name for joining against evidence.

    Values may be PrincipleScore dataclasses or plain dicts; we normalise to
    dicts via ``to_camel_dict`` so downstream code can use uniform access.
    """
    lookup: dict = {}
    for item in per_principle_scores.values():
        raw = to_camel_dict(item) if not isinstance(item, dict) else item
        key = raw.get("displayName") or raw.get("display_name", "")
        if key:
            lookup[key] = raw
    return lookup


def extract_scores(scores: ScoringResult | dict | None) -> tuple[dict, dict]:
    """Extract per-principle scores and aggregate from a ScoringResult or dict."""
    if not scores:
        return {}, {}
    if isinstance(scores, dict):
        return scores.get("principles", {}), scores.get("overall", {})
    return scores.principles, to_camel_dict(scores.overall) if scores.overall else {}
