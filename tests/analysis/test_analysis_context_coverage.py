"""Tests for _analysis_context.py — error logging in _load_custom_dimensions."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from quodeq.analysis._analysis_context import _load_custom_dimensions


def _enable_propagation():
    """Return the quodeq logger with propagate=True (restored by caller)."""
    logger = logging.getLogger("quodeq")
    original = logger.propagate
    logger.propagate = True
    return logger, original


class TestLoadCustomDimensions:
    def test_valid_json_files_are_included(self, tmp_path: Path):
        ev = tmp_path / "evaluators"
        ev.mkdir()
        (ev / "custom.json").write_text(json.dumps({"id": "custom-dim"}), encoding="utf-8")
        result = _load_custom_dimensions(ev, ["existing"])
        assert "custom-dim" in result

    def test_oserror_reading_file_logs_warning_and_skips(self, tmp_path: Path, monkeypatch, caplog):
        """#538 — OSError while reading evaluator file must be logged, not swallowed."""
        ev = tmp_path / "evaluators"
        ev.mkdir()
        bad_file = ev / "broken.json"
        bad_file.write_text("{}", encoding="utf-8")

        def _bad_read_text(self, *args, **kwargs):
            raise OSError("read error")

        monkeypatch.setattr(Path, "read_text", _bad_read_text)
        quodeq_logger, orig = _enable_propagation()
        try:
            with caplog.at_level(logging.WARNING, logger="quodeq.analysis._analysis_context"):
                result = _load_custom_dimensions(ev, [])
        finally:
            quodeq_logger.propagate = orig

        assert result == []
        assert "Skipping custom evaluator" in caplog.text
        assert "broken.json" in caplog.text

    def test_invalid_json_logs_warning_and_skips(self, tmp_path: Path, caplog):
        """#538 — ValueError (bad JSON) must be logged, not swallowed."""
        ev = tmp_path / "evaluators"
        ev.mkdir()
        (ev / "malformed.json").write_text("NOT JSON", encoding="utf-8")

        quodeq_logger, orig = _enable_propagation()
        try:
            with caplog.at_level(logging.WARNING, logger="quodeq.analysis._analysis_context"):
                result = _load_custom_dimensions(ev, [])
        finally:
            quodeq_logger.propagate = orig

        assert result == []
        assert "Skipping custom evaluator" in caplog.text
        assert "malformed.json" in caplog.text
