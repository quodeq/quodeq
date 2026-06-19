"""Tests for builder.py — _load_evaluation_rules logs on template load failure."""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis.prompts.builder import _load_evaluation_rules


def _enable_propagation():
    logger = logging.getLogger("quodeq")
    original = logger.propagate
    logger.propagate = True
    return logger, original


class TestLoadEvaluationRulesLogging:
    def test_oserror_loading_template_logs_warning(self, caplog):
        """#157 — OSError on template load must be logged before continuing."""

        def _bad_load(template_name):
            raise OSError(f"Cannot read {template_name}")

        quodeq_logger, orig = _enable_propagation()
        try:
            with patch(
                "quodeq.analysis.prompts.builder.load_template", side_effect=_bad_load
            ):
                with caplog.at_level(logging.WARNING, logger="quodeq.analysis.prompts.builder"):
                    result = _load_evaluation_rules()
        finally:
            quodeq_logger.propagate = orig

        # Result is empty (both templates failed) — safe fallback preserved
        assert result == ""
        assert "Failed to load prompt template" in caplog.text

    def test_returns_content_when_one_template_loads(self, caplog):
        """#157 — partial load still returns the available template content."""
        call_count = [0]

        def _partial_load(template_name):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("missing first file")
            return "format rules"

        quodeq_logger, orig = _enable_propagation()
        try:
            with patch(
                "quodeq.analysis.prompts.builder.load_template", side_effect=_partial_load
            ):
                with caplog.at_level(logging.WARNING, logger="quodeq.analysis.prompts.builder"):
                    result = _load_evaluation_rules()
        finally:
            quodeq_logger.propagate = orig

        assert result == "format rules"
        assert "Failed to load prompt template" in caplog.text
