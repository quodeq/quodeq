"""Tests for dry-run mode — pipeline skips AI calls and produces minimal valid output."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.core.evidence.model import Evidence


# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------

def _make_dims_data(*dimension_ids: str) -> dict:
    return {"applies": [{"id": d} for d in dimension_ids]}


def _make_config(tmp_path: Path, *, dry_run: bool = False, dimensions: list[str] | None = None) -> RunConfig:
    return RunConfig(
        src=tmp_path / "src",
        language="python",
        work_dir=tmp_path / "evidence",
        dimensions_data=_make_dims_data("security", "reliability"),
        options=AnalysisOptions(
            dry_run=dry_run,
            dimensions=dimensions,
        ),
    )


# ---------------------------------------------------------------------------
# AnalysisOptions: dry_run field
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CLI wiring: dry_run propagates from args to AnalysisOptions
# ---------------------------------------------------------------------------

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
            _single_file=False,
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
            _single_file=False,
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
            _single_file=False,
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


# ---------------------------------------------------------------------------
# Pipeline: dry-run skips AI calls
# ---------------------------------------------------------------------------

class TestDryRunPipeline:
    def _make_config(self, tmp_path: Path, *, dimensions: list[str] | None = None) -> RunConfig:
        (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        return RunConfig(
            src=tmp_path / "src",
            language="python",
            work_dir=tmp_path / "evidence",
            dimensions_data=_make_dims_data("security", "reliability"),
            options=AnalysisOptions(dry_run=True, dimensions=dimensions),
        )

    def test_no_ai_calls_made(self, tmp_path):
        """Dry-run should never construct a DimensionRunner or invoke any AI runner."""
        config = self._make_config(tmp_path)

        with patch("quodeq.analysis._pipeline.DimensionRunner") as mock_runner_cls, \
             patch("quodeq.analysis._pipeline.emit_marker"), \
             patch("quodeq.analysis._pipeline.load_analysis_context") as mock_ctx:
            dims = ["security", "reliability"]
            ctx = MagicMock()
            ctx.total = 2
            mock_ctx.return_value = (dims, ctx)

            from quodeq.analysis._pipeline import run_per_dimension
            result = run_per_dimension(config)

        mock_runner_cls.assert_not_called()
        assert set(result.keys()) == {"security", "reliability"}

    def test_returns_evidence_per_dimension(self, tmp_path):
        """Each dimension gets an Evidence object with correct metadata."""
        config = self._make_config(tmp_path)

        with patch("quodeq.analysis._pipeline.emit_marker"), \
             patch("quodeq.analysis._pipeline.load_analysis_context") as mock_ctx:
            dims = ["security", "reliability"]
            ctx = MagicMock()
            ctx.total = 2
            mock_ctx.return_value = (dims, ctx)

            from quodeq.analysis._pipeline import run_per_dimension
            result = run_per_dimension(config)

        for dim in ["security", "reliability"]:
            assert dim in result
            ev = result[dim]
            assert isinstance(ev, Evidence)
            assert ev.language == "python"
            assert ev.files_read == 0
            assert ev.coverage_pct == 0.0

    # Removed test_fingerprints_saved_per_dimension: V1's per-dimension
    # fingerprint write is gone. V2 writes per-file cache entries during
    # dispatch, and dry-run doesn't dispatch — no cache state to assert.

    def test_on_dimension_done_callback_called(self, tmp_path):
        """on_dimension_done callback receives each dimension and its Evidence."""
        config = self._make_config(tmp_path)
        done_calls: list[tuple[str, Evidence]] = []

        with patch("quodeq.analysis._pipeline.emit_marker"), \
             patch("quodeq.analysis._pipeline.load_analysis_context") as mock_ctx:
            dims = ["security", "reliability"]
            ctx = MagicMock()
            ctx.total = 2
            mock_ctx.return_value = (dims, ctx)

            from quodeq.analysis._pipeline import run_per_dimension
            run_per_dimension(config, on_dimension_done=lambda d, ev: done_calls.append((d, ev)))

        assert len(done_calls) == 2
        assert done_calls[0][0] == "security"
        assert done_calls[1][0] == "reliability"

    def test_run_returns_merged_evidence(self, tmp_path):
        """run() in dry-run mode returns a single merged Evidence."""
        config = self._make_config(tmp_path)

        with patch("quodeq.analysis._pipeline.emit_marker"), \
             patch("quodeq.analysis._pipeline.load_analysis_context") as mock_ctx:
            dims = ["security", "reliability"]
            ctx = MagicMock()
            ctx.total = 2
            mock_ctx.return_value = (dims, ctx)

            from quodeq.analysis._pipeline import run
            evidence = run(config)

        assert isinstance(evidence, Evidence)
        assert evidence.language == "python"
        assert evidence.principles == {}

    def test_single_dimension_filter(self, tmp_path):
        """Dry-run respects the dimension filter."""
        config = self._make_config(tmp_path, dimensions=["security"])

        with patch("quodeq.analysis._pipeline.emit_marker"), \
             patch("quodeq.analysis._pipeline.load_analysis_context") as mock_ctx:
            dims = ["security"]  # filtered down to just this one
            ctx = MagicMock()
            ctx.total = 1
            mock_ctx.return_value = (dims, ctx)

            from quodeq.analysis._pipeline import run_per_dimension
            result = run_per_dimension(config)

        assert list(result.keys()) == ["security"]

    def test_evidence_files_created_per_dimension(self, tmp_path):
        """Dry-run creates an empty evidence JSONL file for each dimension."""
        config = self._make_config(tmp_path)

        with patch("quodeq.analysis._pipeline.emit_marker"), \
             patch("quodeq.analysis._pipeline.load_analysis_context") as mock_ctx:
            dims = ["security", "reliability"]
            ctx = MagicMock()
            ctx.total = 2
            mock_ctx.return_value = (dims, ctx)

            from quodeq.analysis._pipeline import run_per_dimension
            run_per_dimension(config)

        evidence_dir = tmp_path / "evidence"
        for dim in ["security", "reliability"]:
            jsonl_path = evidence_dir / f"{dim}_evidence.jsonl"
            assert jsonl_path.exists(), f"Expected evidence file {jsonl_path} to exist"

    def test_does_not_raise_zero_findings_error(self, tmp_path):
        """Dry-run with source files present must not raise zero-findings EvaluationError."""
        config = RunConfig(
            src=tmp_path / "src",
            language="python",
            work_dir=tmp_path / "evidence",
            dimensions_data=_make_dims_data("security"),
            options=AnalysisOptions(dry_run=True),
            # simulate a repo with files so check_zero_findings would normally fire
            manifest=MagicMock(total_files=10),
        )
        (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)

        with patch("quodeq.analysis._pipeline.emit_marker"), \
             patch("quodeq.analysis._pipeline.load_analysis_context") as mock_ctx:
            ctx = MagicMock()
            ctx.total = 1
            mock_ctx.return_value = (["security"], ctx)

            from quodeq.analysis._pipeline import run_per_dimension
            # Should not raise — dry-run bypasses check_zero_findings entirely
            result = run_per_dimension(config)

        assert "security" in result
