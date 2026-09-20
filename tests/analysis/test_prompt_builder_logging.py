"""Tests for builder.py — load_evaluation_rules logs on template load failure."""
from __future__ import annotations

import logging

import pytest

from quodeq.analysis.prompts.builder import load_evaluation_rules


@pytest.fixture()
def _propagating_quodeq_logger(monkeypatch):
    """Make the "quodeq" logger propagate to caplog's handler for the
    duration of the test; monkeypatch restores the original value."""
    logger = logging.getLogger("quodeq")
    monkeypatch.setattr(logger, "propagate", True)
    return logger


class TestLoadEvaluationRulesLogging:
    def test_oserror_loading_template_logs_warning(self, caplog, monkeypatch, _propagating_quodeq_logger):
        """#157 — OSError on template load must be logged before continuing."""

        def _bad_load(template_name):
            raise OSError(f"Cannot read {template_name}")

        monkeypatch.setattr("quodeq.analysis.prompts.builder.load_template", _bad_load)
        with caplog.at_level(logging.WARNING, logger="quodeq.analysis.prompts.builder"):
            result = load_evaluation_rules()

        # Result is empty (both templates failed) — safe fallback preserved
        assert result == ""
        assert "Failed to load prompt template" in caplog.text

    def test_returns_content_when_one_template_loads(self, caplog, monkeypatch, _propagating_quodeq_logger):
        """#157 — partial load still returns the available template content."""
        call_count = [0]

        def _partial_load(template_name):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("missing first file")
            return "format rules"

        monkeypatch.setattr("quodeq.analysis.prompts.builder.load_template", _partial_load)
        with caplog.at_level(logging.WARNING, logger="quodeq.analysis.prompts.builder"):
            result = load_evaluation_rules()

        assert result == "format rules"
        assert "Failed to load prompt template" in caplog.text
