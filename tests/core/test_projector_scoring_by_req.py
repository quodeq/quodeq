"""SQL projector path groups findings by ``req`` like the evidence path.

``finding_to_scoring_dict`` fed the tally only ``severity``, ``reason`` and
``vt``; with ``req`` now the primary grouping key the projector would have
diverged from the evidence path (issue #1274). The parity test drives the
expected value through the evidence serialisation (``judgment_to_dict``) and
the actual value through the projector's ``Finding`` mapping, so a key
dropped on either side fails it.
"""
from __future__ import annotations

from quodeq.core.events.models import Judgment
from quodeq.core.evidence.jsonl import judgment_to_dict
from quodeq.core.finding_mappings import judgment_to_finding
from quodeq.core.scoring.internals import finding_to_scoring_dict, principle_score_and_grade
from quodeq.core.scoring.principle import compute_tallies
from quodeq.core.scoring.projector_scoring import compute_principle_grade
from tests.core._projector_scoring_fixtures import _f

_PRINCIPLE = "analyzability"
_DIMENSION = "maintainability"
_VIOLATION_COUNT = 12
_COMPLIANCE_COUNT = 3


def _judgment(req: str, reason: str, verdict: str = "violation", vt: str | None = None) -> Judgment:
    return Judgment(
        practice_id=_PRINCIPLE, verdict=verdict, dimension=_DIMENSION, file="a.py",
        line=1, reason=reason, severity="minor", req=req, violation_type=vt,
    )


def test_finding_to_scoring_dict_carries_req():
    d = finding_to_scoring_dict(_f("M-ANA-9", _PRINCIPLE, severity="minor"))
    assert d["req"] == "M-ANA-9"
    assert "vt" not in d


def test_finding_to_scoring_dict_omits_blank_req():
    d = finding_to_scoring_dict(_f("", _PRINCIPLE, severity="minor"))
    assert "req" not in d


def test_projector_and_evidence_agree_by_req():
    violations = [
        _judgment("M-ANA-9", f"reason {i}", vt=f"tag-{i}") for i in range(_VIOLATION_COUNT)
    ]
    compliance = [
        _judgment("M-ANA-1", f"ok {i}", verdict="compliance") for i in range(_COMPLIANCE_COUNT)
    ]

    # Evidence path: the JSONL dict shape the CLI scorer tallies.
    vt_counts, ct_counts, _ = compute_tallies(
        [judgment_to_dict(j) for j in violations],
        [judgment_to_dict(j) for j in compliance],
    )
    assert vt_counts["minor"] == 1  # twelve vt spellings, one requirement
    expected_score, expected_grade = principle_score_and_grade(vt_counts, ct_counts)

    # SQL path: the Finding shape the projector scores.
    projector = compute_principle_grade(
        principle_id=_PRINCIPLE,
        findings=[judgment_to_finding(j) for j in violations],
        compliance=[judgment_to_finding(j) for j in compliance],
    )
    assert projector["score"] == expected_score
    assert projector["grade"] == expected_grade
