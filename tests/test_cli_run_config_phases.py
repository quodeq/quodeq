"""Unit tests for the run-config phase helpers in quodeq._cli_run_config.

``_resolve_limits`` owns the flag/env-derived caps; ``_build_analysis_options``
maps them plus the resolved per-run locals onto an ``AnalysisOptions``.
"""

from __future__ import annotations

import argparse

import pytest

class TestResolveLimits:
    """_resolve_limits owns every env/flag-derived cap _build_run_config needs."""

    def _args(self, **over):
        base = dict(
            no_verify=False, max_turns=None, max_duration=None, n_subagents=5,
            pool_budget=None, clean_scan=False, diff_from=None, dry_run=False,
        )
        base.update(over)
        return argparse.Namespace(**base)

    @pytest.fixture()
    def _cli_over_env_limits(self):
        from quodeq._cli_run_config import _resolve_limits

        return _resolve_limits(
            self._args(max_turns=10, max_duration=300, pool_budget=120, n_subagents=3),
            env={"QUODEQ_MAX_TURNS": "99", "QUODEQ_MAX_DURATION": "99"},
        )

    def test_cli_flags_win_over_env(self, _cli_over_env_limits):
        limits = _cli_over_env_limits
        assert limits.max_turns == 10
        assert limits.max_duration == 300
        assert limits.max_subagents == 3
        assert limits.time_limit == 120

    def test_cli_flags_win_over_env_leaves_unrelated_defaults_untouched(self, _cli_over_env_limits):
        """Unrelated caps must keep their defaults regardless of the
        max_turns/max_duration/time_limit precedence exercised above."""
        limits = _cli_over_env_limits
        assert limits.verify_findings is True
        assert limits.dry_run is False
        assert limits.dispatch_policy is not None

    def test_env_fills_in_unset_caps(self):
        from quodeq._cli_run_config import _resolve_limits

        limits = _resolve_limits(
            self._args(), env={"QUODEQ_MAX_TURNS": "7", "QUODEQ_NO_VERIFY": "1"},
        )

        assert limits.max_turns == 7
        assert limits.verify_findings is False

    def test_clean_scan_and_diff_from_disable_incremental(self):
        from quodeq._cli_run_config import _resolve_limits

        assert _resolve_limits(self._args(), env={}).incremental is True
        assert _resolve_limits(self._args(clean_scan=True), env={}).incremental is False
        assert _resolve_limits(self._args(diff_from="HEAD~1"), env={}).incremental is False


class TestBuildAnalysisOptions:
    def test_maps_resolved_locals_and_limits_onto_the_options(self):
        from quodeq.cli_evaluation import _RunConfigLocals
        from quodeq._cli_run_config import _build_analysis_options, _resolve_limits

        limits = _resolve_limits(
            argparse.Namespace(
                no_verify=True, max_turns=4, max_duration=8, n_subagents=2,
                pool_budget=None, clean_scan=True, diff_from=None, dry_run=True,
            ),
            env={},
        )
        resolved = _RunConfigLocals(
            consolidated=False,
            effective_ai_model="claude-3",
            subagent_model="ollama/llama3",
            diff_from="HEAD~1",
            diff_files={"a.py"},
            skip_scoring=True,
        )

        options = _build_analysis_options(["security"], resolved, limits)

        assert options.ai_model == "claude-3"
        assert options.dimensions == ["security"]
        assert options.subagent_model == "ollama/llama3"
        assert options.consolidated is False
        assert options.diff_from == "HEAD~1"
        assert options.incremental_file_filter == {"a.py"}
        assert options.skip_scoring is True
        assert options.max_turns == 4
        assert options.max_duration == 8
        assert options.max_subagents == 2
        assert options.verify_findings is False
        assert options.incremental is False
        assert options.dry_run is True
