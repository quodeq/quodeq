"""Tests for dry-run mode — the AnalysisOptions field and CLI arg wiring.

Split from test_dry_run.py: dry_run field defaults/independence, and
dry_run propagating from CLI args to AnalysisOptions (including the
getattr fallback when args has no dry_run attribute at all). Shared
helpers live in tests/analysis/_dry_run_fixtures.py.
"""
from __future__ import annotations

import argparse
from unittest.mock import patch

from quodeq.analysis._types import AnalysisOptions

from tests.analysis._dry_run_fixtures import _make_dims_data


class TestAnalysisOptionsDryRun:
    def test_default_is_false(self):
        opts = AnalysisOptions()
        assert opts.dry_run is False

    def test_can_be_set_true(self):
        opts = AnalysisOptions(dry_run=True)
        assert opts.dry_run is True

    def test_other_fields_unaffected(self):
        opts = AnalysisOptions(dry_run=True, incremental=True)
        assert opts.incremental is True
        assert opts.dry_run is True


class TestCliWiring:
    def test_dry_run_wired_from_args(self, tmp_path):
        from quodeq._cli_evaluation import _build_run_config
        from quodeq._cli_resolution import ResolvedInputs

        args = argparse.Namespace(
            dimensions=None,
            max_turns=None,
            max_duration=None,
            n_subagents=1,
            pool_budget=None,
            incremental=False,
            no_verify=False,
            no_consolidated=False,
            dry_run=True,
        )

        dims_data = _make_dims_data("security")
        inputs = ResolvedInputs(
            src=tmp_path,
            language="python",
            manifest=None,
            dims_data=dims_data,
        )

        with patch("quodeq._cli_evaluation.default_paths") as mock_paths, \
             patch("quodeq._cli_evaluation.get_ai_model", return_value=None), \
             patch("quodeq._cli_evaluation._subagent_model", return_value=None):
            mock_paths.return_value.standards_dir = tmp_path / "standards"
            mock_paths.return_value.evaluators_dir = tmp_path / "evaluators"
            config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path / "evidence")

        assert config.options.dry_run is True

    def test_dry_run_false_by_default(self, tmp_path):
        from quodeq._cli_evaluation import _build_run_config
        from quodeq._cli_resolution import ResolvedInputs

        args = argparse.Namespace(
            dimensions=None,
            max_turns=None,
            max_duration=None,
            n_subagents=1,
            pool_budget=None,
            incremental=False,
            no_verify=False,
            no_consolidated=False,
            dry_run=False,
        )

        dims_data = _make_dims_data("security")
        inputs = ResolvedInputs(
            src=tmp_path,
            language="python",
            manifest=None,
            dims_data=dims_data,
        )

        with patch("quodeq._cli_evaluation.default_paths") as mock_paths, \
             patch("quodeq._cli_evaluation.get_ai_model", return_value=None), \
             patch("quodeq._cli_evaluation._subagent_model", return_value=None):
            mock_paths.return_value.standards_dir = tmp_path / "standards"
            mock_paths.return_value.evaluators_dir = tmp_path / "evaluators"
            config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path / "evidence")

        assert config.options.dry_run is False

    def test_missing_dry_run_attr_defaults_false(self, tmp_path):
        """getattr fallback: if args has no dry_run attribute, default to False."""
        from quodeq._cli_evaluation import _build_run_config
        from quodeq._cli_resolution import ResolvedInputs

        args = argparse.Namespace(
            dimensions=None,
            max_turns=None,
            max_duration=None,
            n_subagents=1,
            pool_budget=None,
            incremental=False,
            no_verify=False,
            no_consolidated=False,
            # no dry_run attribute at all
        )

        dims_data = _make_dims_data("security")
        inputs = ResolvedInputs(
            src=tmp_path,
            language="python",
            manifest=None,
            dims_data=dims_data,
        )

        with patch("quodeq._cli_evaluation.default_paths") as mock_paths, \
             patch("quodeq._cli_evaluation.get_ai_model", return_value=None), \
             patch("quodeq._cli_evaluation._subagent_model", return_value=None):
            mock_paths.return_value.standards_dir = tmp_path / "standards"
            mock_paths.return_value.evaluators_dir = tmp_path / "evaluators"
            config = _build_run_config(args, inputs=inputs, evidence_dir=tmp_path / "evidence")

        assert config.options.dry_run is False
