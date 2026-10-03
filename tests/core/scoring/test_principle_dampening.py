"""The graded-mode dampening is computed only where graded mode reads it."""
from __future__ import annotations

from quodeq.core.scoring import principle
from quodeq.core.scoring.overall import MODE_NUMERICAL

_GRADED = "graded"


def _principles(n: int) -> dict:
    return {
        f"P{i}": {"metrics": {"confidence_level": "high"},
                  "violations": [{"severity": "minor", "reason": "r"}],
                  "compliance": [{"severity": "minor", "reason": "c"}]}
        for i in range(n)
    }


def _count_dampening(monkeypatch) -> list[int]:
    calls: list[int] = []
    real = principle.compliance_dampening

    def counting(ct, vt):
        calls.append(1)
        return real(ct, vt)

    monkeypatch.setattr(principle, "compliance_dampening", counting)
    return calls


def test_numerical_mode_never_computes_dampening(monkeypatch):
    calls = _count_dampening(monkeypatch)
    principle.score_all_principles(_principles(3), MODE_NUMERICAL, 1, 10)
    assert calls == []


def test_graded_mode_computes_dampening_once_per_principle(monkeypatch):
    calls = _count_dampening(monkeypatch)
    scores = principle.score_all_principles(_principles(3), _GRADED, 1, 10)
    assert len(calls) == 3
    assert all(s.dampening_multiplier is not None for s in scores.values())
