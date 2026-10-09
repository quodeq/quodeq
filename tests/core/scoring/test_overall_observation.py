"""The dimension score weighs principles by observation, not one each."""
from __future__ import annotations

from quodeq.core.scoring.overall import MODE_NUMERICAL, weighted_overall
from quodeq.core.types.scoring import PrincipleScore


def _p(score, observation, confidence="high", weight="Medium (x2)"):
    return PrincipleScore(display_name="p", weight=weight, final_score=score, grade="Good",
                          observation=observation, confidence_level=confidence)


def test_a_thin_ten_barely_moves_the_dimension():
    heavy = _p(4.6, 400.0)
    thin = _p(10.0, 1.3, confidence="low")
    alone = weighted_overall({"a": heavy}, MODE_NUMERICAL).weighted_score
    both = weighted_overall({"a": heavy, "b": thin}, MODE_NUMERICAL).weighted_score
    assert alone == 4.6 and 4.6 <= both <= 4.7


def test_configured_multiplier_still_applies():
    a = _p(4.0, 10.0, weight="Low (x1)")
    b = _p(8.0, 10.0, weight="High (x3)")
    assert weighted_overall({"a": a, "b": b}, MODE_NUMERICAL).weighted_score == 7.0


def test_low_confidence_note_when_most_observation_is_thin():
    a = _p(9.0, 1.0, confidence="low")
    b = _p(9.0, 1.0, confidence="low")
    c = _p(5.0, 1.5, confidence="high")
    out = weighted_overall({"a": a, "b": b, "c": c}, MODE_NUMERICAL)
    assert out.confidence == "low" and "Thin evidence" in (out.confidence_reason or "")
    assert weighted_overall({"c": c}, MODE_NUMERICAL).confidence is None


def test_zero_observation_everywhere_falls_back_to_equal_weights():
    out = weighted_overall({"a": _p(4.0, 0.0), "b": _p(8.0, 0.0)}, MODE_NUMERICAL)
    assert out.weighted_score == 6.0
