"""Shared helpers for tests/core/test_projector_scoring_*.py siblings.

Split out of test_projector_scoring.py.
"""
from __future__ import annotations

from quodeq.core.types.finding import Finding


def _f(req: str, principle: str, severity: str = "medium", verdict: str = "violation") -> Finding:
    return Finding(
        practice_id=principle, verdict=verdict, file="a.py", line=1,
        end_line=1, title="t", reason="r", snippet="s", severity=severity,
        cwe=None, req=req, req_refs=[], context="", dimension="Security",
        violation_type=None, scope="", confidence=100,
    )
