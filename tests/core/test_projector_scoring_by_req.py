"""SQL projector path groups untagged findings by ``req`` like the evidence path.

``finding_to_scoring_dict`` fed the tally only ``severity``, ``reason`` and
``vt``; with no ``vt`` the projector grouped by reason and diverged from the
evidence path once the tally learned to group by ``req`` (issue #1274).
"""
from __future__ import annotations

from dataclasses import replace

from quodeq.core.scoring.internals import finding_to_scoring_dict, principle_score_and_grade
from quodeq.core.scoring.principle import compute_tallies
from quodeq.core.scoring.projector_scoring import compute_principle_grade
from tests.core._projector_scoring_fixtures import _f

_PRINCIPLE = "analyzability"
_VIOLATION_COUNT = 12
_COMPLIANCE_COUNT = 3


def test_finding_to_scoring_dict_carries_req():
    d = finding_to_scoring_dict(_f("M-ANA-9", _PRINCIPLE, severity="minor"))
    assert d["req"] == "M-ANA-9"
    assert "vt" not in d


def test_finding_to_scoring_dict_omits_blank_req():
    d = finding_to_scoring_dict(_f("", _PRINCIPLE, severity="minor"))
    assert "req" not in d


def test_projector_and_evidence_agree_by_req():
    findings = [
        replace(_f("M-ANA-9", _PRINCIPLE, severity="minor"), reason=f"reason {i}")
        for i in range(_VIOLATION_COUNT)
    ]
    compliance = [
        replace(_f("M-ANA-1", _PRINCIPLE, verdict="compliance"), reason=f"ok {i}")
        for i in range(_COMPLIANCE_COUNT)
    ]
    projector = compute_principle_grade(
        principle_id=_PRINCIPLE, findings=findings, compliance=compliance,
    )
    v_dicts = [finding_to_scoring_dict(f) for f in findings]
    c_dicts = [finding_to_scoring_dict(c) for c in compliance]
    vt_counts, ct_counts, _ = compute_tallies(v_dicts, c_dicts)
    assert vt_counts["minor"] == 1
    score, grade = principle_score_and_grade(vt_counts, ct_counts)
    assert projector["score"] == score
    assert projector["grade"] == grade
