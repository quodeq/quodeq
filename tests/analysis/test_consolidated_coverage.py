"""Tests for subagents/_consolidated.py — config building, prompt, result collection."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.subagents._consolidated import (
    _build_consolidated_config,
    _build_prompt,
    _ConsolidatedPaths,
)


# ---------------------------------------------------------------------------
# Helper: minimal RunConfig mock
# ---------------------------------------------------------------------------

@dataclass
class _MockOptions:
    subagent_model: str | None = None
    ai_model: str = "sonnet-4"
    analysis_budget: str | None = None
    max_turns: int | None = None
    max_duration: int | None = None
    pool_budget: int | None = None
    max_subagents: int = 3
    deadline_at: float | None = None


@dataclass
class _MockTarget:
    name: str = "auth-module"


@dataclass
class _MockRunConfig:
    language: str = "python"
    src: Path = Path("/repo")
    work_dir: Path | None = None
    standards_dir: Path | None = None
    evaluators_dir: Path | None = None
    manifest: object = None
    target: _MockTarget | None = None
    source_file_count: int = 100
    options: _MockOptions = field(default_factory=_MockOptions)


@dataclass
class _MockCtx:
    date_str: str = "2026-04-09"
    dimensions_data: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# _build_consolidated_config
# ---------------------------------------------------------------------------

class TestBuildConsolidatedConfig:
    def test_basic_config(self):
        config = _MockRunConfig()
        with patch("quodeq.analysis.subagents._consolidated._default_subagent_model", return_value=None):
            ac = _build_consolidated_config(config, ["security", "reliability"], 10)
        assert ac.dimension == "security,reliability"
        assert ac.max_files_per_agent == 10
        assert ac.ai_model == "sonnet-4"

    def test_uses_subagent_model_when_set(self):
        config = _MockRunConfig(options=_MockOptions(subagent_model="haiku-3"))
        with patch("quodeq.analysis.subagents._consolidated._default_subagent_model", return_value=None):
            ac = _build_consolidated_config(config, ["security"], 5)
        assert ac.ai_model == "haiku-3"

    def test_uses_default_subagent_model(self):
        config = _MockRunConfig(options=_MockOptions(subagent_model=None))
        with patch("quodeq.analysis.subagents._consolidated._default_subagent_model", return_value="opus-3"):
            ac = _build_consolidated_config(config, ["security"], 5)
        assert ac.ai_model == "opus-3"

    def test_pool_budget_default(self):
        config = _MockRunConfig(options=_MockOptions(pool_budget=None))
        with patch("quodeq.analysis.subagents._consolidated._default_subagent_model", return_value=None):
            ac = _build_consolidated_config(config, ["security"], 5)
        # Should use _DEFAULT_POOL_BUDGET
        assert ac.pool_budget > 0

    def test_pool_budget_custom(self):
        config = _MockRunConfig(options=_MockOptions(pool_budget=1200))
        with patch("quodeq.analysis.subagents._consolidated._default_subagent_model", return_value=None):
            ac = _build_consolidated_config(config, ["security"], 5)
        assert ac.pool_budget == 1200

    def test_includes_compiled_dir(self, tmp_path):
        config = _MockRunConfig()
        with patch("quodeq.analysis.subagents._consolidated._default_subagent_model", return_value=None):
            ac = _build_consolidated_config(config, ["security"], 5, compiled_dir=tmp_path)
        assert ac.compiled_dir == tmp_path

    def test_forwards_budget_and_turns(self):
        config = _MockRunConfig(options=_MockOptions(analysis_budget="5.00", max_turns=50, max_duration=900))
        with patch("quodeq.analysis.subagents._consolidated._default_subagent_model", return_value=None):
            ac = _build_consolidated_config(config, ["security"], 5)
        assert ac.analysis_budget == "5.00"
        assert ac.max_turns == 50
        assert ac.max_duration == 900


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_returns_string(self):
        config = _MockRunConfig()
        ctx = _MockCtx()
        with patch("quodeq.analysis.subagents._consolidated.build_consolidated_prompt", return_value="test prompt") as mock_build:
            result = _build_prompt(config, ["security", "reliability"], ctx)
        assert result == "test prompt"
        mock_build.assert_called_once()

    def test_passes_correct_context(self):
        config = _MockRunConfig(language="typescript", source_file_count=200)
        ctx = _MockCtx(date_str="2026-01-01")
        with patch("quodeq.analysis.subagents._consolidated.build_consolidated_prompt") as mock_build:
            mock_build.return_value = "prompt"
            _build_prompt(config, ["security"], ctx)
        call_kwargs = mock_build.call_args
        prompt_ctx = call_kwargs.kwargs.get("context") or call_kwargs.args[1]
        assert prompt_ctx.language == "typescript"
        assert prompt_ctx.date_str == "2026-01-01"
        assert prompt_ctx.source_file_count == 200


# ---------------------------------------------------------------------------
# _ConsolidatedPaths
# ---------------------------------------------------------------------------

class TestConsolidatedPaths:
    def test_defaults(self, tmp_path):
        paths = _ConsolidatedPaths(evidence_dir=tmp_path)
        assert paths.evidence_dir == tmp_path
        assert paths.compiled_dir is None

    def test_with_compiled_dir(self, tmp_path):
        compiled = tmp_path / "compiled"
        paths = _ConsolidatedPaths(evidence_dir=tmp_path, compiled_dir=compiled)
        assert paths.compiled_dir == compiled
