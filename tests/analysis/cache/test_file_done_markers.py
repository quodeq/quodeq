from __future__ import annotations
import json
from pathlib import Path

from quodeq.analysis.cache.dimension_helpers import _group_findings_by_file


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.write_text("".join(json.dumps(l) + "\n" for l in lines))


class TestGroupFindingsByFile:
    def test_returns_tuple_of_grouped_and_ok_files(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        _write_jsonl(jsonl, [
            {"file": "a.py", "req": "X-1", "t": "violation"},
            {"_marker": "file_done", "file": "a.py", "status": "ok"},
        ])
        grouped, ok_files = _group_findings_by_file(jsonl)
        assert ok_files == {"a.py"}
        assert "a.py" in grouped and len(grouped["a.py"]) == 1

    def test_marker_not_included_in_findings(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        _write_jsonl(jsonl, [
            {"file": "a.py", "req": "X-1", "t": "violation"},
            {"_marker": "file_done", "file": "a.py", "status": "ok"},
        ])
        grouped, _ = _group_findings_by_file(jsonl)
        assert all("_marker" not in f for f in grouped["a.py"])

    def test_legacy_jsonl_yields_empty_ok_set(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        _write_jsonl(jsonl, [
            {"file": "a.py", "req": "X-1", "t": "violation"},
            {"file": "b.py", "req": "X-2", "t": "violation"},
        ])
        _, ok_files = _group_findings_by_file(jsonl)
        assert ok_files == set()

    def test_error_marker_does_not_add_to_ok_set(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        _write_jsonl(jsonl, [
            {"_marker": "file_done", "file": "a.py", "status": "error", "reason": "token_limit"},
        ])
        _, ok_files = _group_findings_by_file(jsonl)
        assert ok_files == set()

    def test_ok_then_later_error_treated_as_error(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        _write_jsonl(jsonl, [
            {"_marker": "file_done", "file": "a.py", "status": "ok"},
            {"_marker": "file_done", "file": "a.py", "status": "error", "reason": "parse_error"},
        ])
        _, ok_files = _group_findings_by_file(jsonl)
        assert ok_files == set()  # last-write-wins, error overrides ok

    def test_malformed_marker_ignored(self, tmp_path: Path):
        jsonl = tmp_path / "evidence.jsonl"
        _write_jsonl(jsonl, [
            {"_marker": "file_done"},  # missing file/status
            {"file": "a.py", "req": "X-1", "t": "violation"},
            {"_marker": "file_done", "file": "a.py", "status": "ok"},
        ])
        grouped, ok_files = _group_findings_by_file(jsonl)
        assert ok_files == {"a.py"}
        assert len(grouped["a.py"]) == 1

    def test_missing_jsonl_returns_empty_pair(self, tmp_path: Path):
        grouped, ok_files = _group_findings_by_file(tmp_path / "missing.jsonl")
        assert grouped == {}
        assert ok_files == set()
