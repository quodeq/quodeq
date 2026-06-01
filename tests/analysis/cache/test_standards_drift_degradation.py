"""Standards-drift safety net for the permissive cache.

The permissive cache reuses findings after a standards edit (standards is no
longer in the cache key — see docs design 2026-06-01). A reused finding can
therefore reference a requirement/standard ID that no longer exists in the
current standards. This is the one real risk called out in the design, so we
pin the guarantee: scoring/grouping must degrade GRACEFULLY on an absent
requirement ID — no crash, no KeyError — at worst the finding becomes an
orphan principle. (Reconciling orphan IDs back to current standards is the
separately-tracked "remap findings to correct req IDs" follow-up.)
"""
from __future__ import annotations

from quodeq.core.evidence._req_mapping import _group_judgments
from quodeq.core.evidence.model import Evidence, PrincipleEvidence
from quodeq.core.events.models import Judgment
from quodeq.core.scoring.engine import score_evidence


def _ghost_judgment() -> Judgment:
    # practice_id that exists in no current standard (the reused-finding case).
    return Judgment(
        practice_id="GHOST-1",
        verdict="violation",
        dimension="security",
        file="src/ghost.py",
        line=42,
        reason="references a requirement that no longer exists",
        severity="high",
    )


def test_grouping_does_not_crash_on_absent_requirement_id():
    # With no current mappings, an unknown practice_id falls back to itself
    # (orphan principle) instead of raising.
    grouped = _group_judgments([_ghost_judgment()], dimension="security", evaluators_dir=None)
    assert "GHOST-1" in grouped.violations
    assert len(grouped.violations["GHOST-1"]) == 1


def test_scoring_does_not_crash_on_orphan_principle():
    orphan = PrincipleEvidence(
        practice_id="GHOST-1",
        display_name="GHOST-1",
        dimension="security",
        severity="high",
        violations=[{"file": "src/ghost.py", "line": 42, "reason": "absent req"}],
        compliance=[],
        metrics={
            "total_instances": 1, "compliant": 0, "violating": 1,
            "compliance_percentage": 0.0, "confidence_level": "low",
            "is_balanced": False,
        },
    )
    evidence = Evidence(
        repository="test", language="python", date="2026-06-01",
        source_file_count=10, files_read=5, coverage_pct=50.0,
        principles={"GHOST-1": orphan},
    )
    # The assertion that matters: this returns instead of raising.
    result = score_evidence(evidence, mode="numerical")
    assert "GHOST-1" in result.principles
