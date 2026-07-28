"""Tests for _analysis_context.py — error logging in _load_custom_dimensions."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from quodeq.analysis._analysis_context import _load_custom_dimensions, load_analysis_context
from quodeq.analysis._types import AnalysisOptions, RunConfig


def _enable_propagation():
    """Return the quodeq logger with propagate=True (restored by caller)."""
    logger = logging.getLogger("quodeq")
    original = logger.propagate
    logger.propagate = True
    return logger, original


def _config(tmp_path: Path, requested: list[str]) -> RunConfig:
    return RunConfig(
        src=tmp_path,
        language="python",
        options=AnalysisOptions(dimensions=requested),
        dimensions_data={
            "applies": [{"id": "security"}, {"id": "maintainability"}, {"id": "flexibility"}],
        },
        evaluators_dir=tmp_path / "no-evaluators",
    )


class TestDimensionResolutionOrder:
    def test_requested_order_is_preserved(self, tmp_path: Path):
        """#912 — dims must run in the order the user selected, not config order."""
        dimensions, _ctx = load_analysis_context(_config(tmp_path, ["flexibility", "maintainability"]))
        assert dimensions == ["flexibility", "maintainability"]

    def test_unknown_dimensions_are_dropped_without_reordering(self, tmp_path: Path):
        dimensions, _ctx = load_analysis_context(_config(tmp_path, ["flexibility", "bogus", "security"]))
        assert dimensions == ["flexibility", "security"]

    def test_duplicate_requests_are_deduped(self, tmp_path: Path):
        dimensions, _ctx = load_analysis_context(_config(tmp_path, ["flexibility", "flexibility"]))
        assert dimensions == ["flexibility"]


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

    def test_non_dict_json_logs_warning_and_skips(self, tmp_path: Path, caplog):
        """A top-level JSON array (or any non-dict) must not crash on .get("id")."""
        ev = tmp_path / "evaluators"
        ev.mkdir()
        (ev / "array.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

        quodeq_logger, orig = _enable_propagation()
        try:
            with caplog.at_level(logging.WARNING, logger="quodeq.analysis._analysis_context"):
                result = _load_custom_dimensions(ev, ["existing"])
        finally:
            quodeq_logger.propagate = orig

        # Pre-existing dimensions are preserved; the bad file is skipped, not fatal.
        assert result == ["existing"]
        assert "Skipping custom evaluator" in caplog.text
        assert "array.json" in caplog.text
