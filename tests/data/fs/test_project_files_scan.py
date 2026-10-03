"""``scan_json_exists``: a pure presence probe for scan.json, mirroring
``repository_info_exists``.
"""
from __future__ import annotations

from quodeq.data.fs.project_files import scan_json_exists


def test_true_when_scan_json_exists(tmp_path):
    (tmp_path / "scan.json").write_text("{}", encoding="utf-8")
    assert scan_json_exists(tmp_path) is True


def test_false_when_missing(tmp_path):
    assert scan_json_exists(tmp_path) is False


def test_true_even_when_scan_json_is_corrupt(tmp_path):
    """Presence-only: an unreadable scan.json still counts as "has a scan"."""
    (tmp_path / "scan.json").write_text("{not valid json", encoding="utf-8")
    assert scan_json_exists(tmp_path) is True
