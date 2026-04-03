"""Score/grade conversion and score-lookup building for reports."""
from __future__ import annotations

import re

from quodeq.core.types import ScoringResult, to_camel_dict
from quodeq.core.scoring.internals import score_to_grade_label


def grade_from_score(score: str | None) -> str | None:
    """Convert a numeric score string (e.g. '7/10') to a letter grade."""
    if not score:
        return None

    hit = re.match(r"(\d+(?:\.\d+)?)", str(score))
    if not hit:
        return None

    return score_to_grade_label(float(hit.group(1)))


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
