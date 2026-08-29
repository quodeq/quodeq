"""Legacy evaluation/*.json finding-detail reader (SQL twin: findings_queries)."""
from __future__ import annotations

import json

from quodeq.data.fs.report_parser.finding_details import (
    read_finding_details_from_json_eval,
)


def _seed_eval(run_dir, dimension, violations):
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{dimension}.json").write_text(json.dumps({"violations": violations}))


class TestReadFindingDetailsFromJsonEval:
    def test_empty_when_evaluation_dir_absent(self, tmp_path):
        assert read_finding_details_from_json_eval(tmp_path, {("R", "f.py", 1)}) == {}

    def test_maps_fields_and_takes_dimension_from_filename(self, tmp_path):
        _seed_eval(tmp_path, "security", [{
            "req": "S-1", "file": "a.py", "line": 3, "principle": "Input",
            "severity": "major", "title": "t", "reason": "r", "snippet": "s",
            "context": "c", "scope": "prod", "end_line": 5,
            "req_refs": ["S-1a"],
        }])

        out = read_finding_details_from_json_eval(tmp_path, {("S-1", "a.py", 3)})

        assert out == {("S-1", "a.py", 3): {
            "req": "S-1", "file": "a.py", "line": 3,
            "dimension": "security", "principle": "Input",
            "severity": "major", "title": "t", "reason": "r", "snippet": "s",
            "context": "c", "scope": "prod", "endLine": 5, "reqRefs": ["S-1a"],
        }}

    def test_only_requested_keys_and_first_hit_wins(self, tmp_path):
        _seed_eval(tmp_path, "security", [
            {"req": "S-1", "file": "a.py", "line": 1, "title": "wanted"},
            {"req": "S-1", "file": "a.py", "line": 1, "title": "duplicate"},
            {"req": "S-2", "file": "b.py", "line": 2, "title": "unrequested"},
        ])

        out = read_finding_details_from_json_eval(tmp_path, {("S-1", "a.py", 1)})

        assert list(out) == [("S-1", "a.py", 1)]
        assert out[("S-1", "a.py", 1)]["title"] == "wanted"

    def test_unreadable_file_is_skipped(self, tmp_path):
        eval_dir = tmp_path / "evaluation"
        eval_dir.mkdir()
        (eval_dir / "broken.json").write_text("{nope")
        _seed_eval(tmp_path, "security", [{"req": "S-1", "file": "a.py", "line": 1}])

        out = read_finding_details_from_json_eval(tmp_path, {("S-1", "a.py", 1)})
        assert ("S-1", "a.py", 1) in out

    def test_non_int_line_coerces_to_zero(self, tmp_path):
        _seed_eval(tmp_path, "security", [{"req": "S-1", "file": "a.py", "line": "x"}])
        out = read_finding_details_from_json_eval(tmp_path, {("S-1", "a.py", 0)})
        assert out[("S-1", "a.py", 0)]["line"] == 0
