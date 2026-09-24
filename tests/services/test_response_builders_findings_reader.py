"""Test that build_response_from_grade_tables accepts an injected findings_reader."""
from pathlib import Path

from quodeq.services.scoring import build_response_from_grade_tables


class _Tables:
    def __init__(self, _run_dir):
        pass

    def read_dimension_scores(self):
        return [{"dimension": "security", "score": 8.0, "grade": "Good", "exit_reason": None, "files_read": 100}]

    def read_principle_grades(self):
        return []

    def read_run_score_from_dim_scores(self, params=None):
        return {}


def test_findings_come_from_the_injected_reader(tmp_path: Path):
    seen = []

    def reader(run_dir):
        seen.append(run_dir)
        return []

    out = build_response_from_grade_tables(tmp_path, store_factory=_Tables, findings_reader=reader)
    assert seen == [tmp_path]
    assert isinstance(out, dict)
