"""Tests for preview_scores' injectable store_factory seam."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services import grade_formula


class _FakeTables:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir

    def read_dimension_scores(self):
        return [{"dimension": "security", "score": 8.0, "grade": "Good", "exit_reason": None}]

    def read_principle_grades(self):
        return []

    def read_run_score_from_dim_scores(self, params=None):
        return {}


def test_preview_uses_injected_store(tmp_path: Path, monkeypatch):
    run = tmp_path / "proj" / "run1"
    run.mkdir(parents=True)
    (run / "events.jsonl").write_text("")
    seen = []

    def factory(run_dir):
        seen.append(run_dir)
        return _FakeTables(run_dir)

    monkeypatch.setattr(grade_formula, "compute_run_grades", lambda run_dir, params: (None, []))
    out = grade_formula.preview_scores(tmp_path, "proj", DEFAULT_PARAMS, store_factory=factory)
    assert seen == [run]
    assert out["before"]["dimensions"][0]["dimension"] == "security"
