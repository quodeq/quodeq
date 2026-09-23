"""Tests for _fs_metadata.py — read_scan_summary.

Split from test_fs_metadata.py.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services._fs_metadata import read_scan_summary


class TestReadScanSummary:
    def test_reads_scan_data(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "scan.json").write_text(json.dumps({
            "scanned_at": "2026-01-01",
            "total_files": 42,
        }))
        result = read_scan_summary(tmp_path, "proj")
        assert result["scanDate"] == "2026-01-01"
        assert result["totalFiles"] == 42

    def test_returns_empty_if_missing(self, tmp_path: Path):
        assert read_scan_summary(tmp_path, "nope") == {}

    def test_returns_empty_on_bad_json(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "scan.json").write_text("bad json")
        assert read_scan_summary(tmp_path, "proj") == {}
