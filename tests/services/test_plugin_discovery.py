"""Tests for quodeq.services.plugin_discovery."""
from __future__ import annotations

import logging

from quodeq.services.plugin_discovery import _discover_from_detection


def test_malformed_detection_json_degrades_like_dimensions_json(tmp_path, caplog):
    bad = tmp_path / "detection.json"
    bad.write_text("{not valid json", encoding="utf-8")
    dims = tmp_path / "dimensions.json"
    dims.write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = _discover_from_detection(bad, dims)
    assert result == []  # matches whatever the sibling read's fallback returns
    assert "detection.json" in caplog.text


def test_missing_detection_json_degrades_gracefully(tmp_path, caplog):
    missing = tmp_path / "does_not_exist.json"
    dims = tmp_path / "dimensions.json"
    dims.write_text("{}", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        result = _discover_from_detection(missing, dims)
    assert result == []
    assert "detection.json" in caplog.text
