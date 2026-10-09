from __future__ import annotations

from quodeq.services.scoring import build_dimension_dict


def test_dimension_dict_carries_principle_and_dimension_confidence() -> None:
    out = build_dimension_dict(
        {"dimension": "Security", "score": 7.1, "grade": "Good", "files_read": 10, "confidence": "low"},
        [{"principle_id": "P1", "score": 10.0, "grade": "Exemplary", "finding_count": 0, "dismissed_count": 0, "confidence": "low"}],
        [], [],
    )
    assert out["confidence"] == "low"
    assert out["principles"][0] == {"principle": "P1", "score": "10.0/10", "grade": "Exemplary", "confidence": "low"}
