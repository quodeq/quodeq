"""Tests for analysis._report_io — atomic report persistence.

Dashboard readers poll evaluation/<dim>.json every 250ms-2s and treat a parse
failure as "dimension does not exist", so a report write must never expose a
truncated or partial file at the destination path.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from quodeq.analysis._report_io import _persist_json


class TestPersistJsonAtomicity:
    def test_writes_valid_json(self, tmp_path):
        target = tmp_path / "security.json"
        _persist_json({"dimension": "security", "totals": {"violationCount": 3}}, target)
        assert json.loads(target.read_text(encoding="utf-8"))["dimension"] == "security"

    def test_failed_publish_preserves_previous_report(self, tmp_path):
        # If the atomic rename fails (disk full, permissions), the previous
        # report must survive untouched and no temp files may be left behind.
        # With a plain write_text the destination is truncated first and a
        # concurrent reader sees a missing/partial dimension.
        target = tmp_path / "security.json"
        _persist_json({"version": 1}, target)

        with patch("quodeq.analysis._report_io.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                _persist_json({"version": 2}, target)

        assert json.loads(target.read_text(encoding="utf-8")) == {"version": 1}
        leftovers = [p for p in tmp_path.iterdir() if p.name != "security.json"]
        assert leftovers == []
