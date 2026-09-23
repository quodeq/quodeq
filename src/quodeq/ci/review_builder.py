"""Build GitHub PR review payloads from evaluation reports.

Re-export facade: the implementation lives in ``violation_classifier``
(current-vs-baseline classification) and ``github_render`` (comment/summary/
verdict rendering). This module stays so existing imports
(``reporter.py``, ``cli.py``, tests) keep working unchanged.
"""
from __future__ import annotations

from quodeq.ci.violation_classifier import normalize_snippet, classify_violations
from quodeq.ci.github_render import (
    ReviewOptions,
    build_review_summary,
    determine_verdict,
    violation_to_comment,
)

__all__ = [
    "normalize_snippet",
    "classify_violations",
    "violation_to_comment",
    "ReviewOptions",
    "build_review_summary",
    "determine_verdict",
]
