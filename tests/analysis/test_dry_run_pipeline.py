"""Tests for dry-run mode — the pipeline skips AI calls and produces minimal
valid output.

Split from test_dry_run.py. Shared helpers live in
tests/analysis/_dry_run_fixtures.py.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.core.evidence.model import Evidence

from tests.analysis._dry_run_fixtures import _make_dims_data


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

    def test_dim_states_marked_done(self, tmp_path):
        """Dry-run must close out dim states like the real loops do.

        The lifecycle flips any dim still pending/running at exit to
        INCOMPLETE and stamps the run exit_reason=incomplete_dimensions.
        A dry run completes every dimension, so each must end at DONE or
        the run reads as truncated.
        """
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        config = RunConfig(
            src=tmp_path / "src",
            language="python",
            work_dir=tmp_path / "evidence",
            run_dir=run_dir,
            dimensions_data=_make_dims_data("security", "reliability"),
            options=AnalysisOptions(dry_run=True),
        )

        with patch("quodeq.analysis._pipeline.emit_marker"), \
             patch("quodeq.analysis._pipeline.load_analysis_context") as mock_ctx:
            dims = ["security", "reliability"]
            ctx = MagicMock()
            ctx.total = 2
            mock_ctx.return_value = (dims, ctx)

            from quodeq.analysis._pipeline import run_per_dimension
            run_per_dimension(config)

        from quodeq.data.fs.dimensions_state_store import read_dimensions
        entries = read_dimensions(run_dir).get("dimensions", {})
        states = {dim: entry.get("state") for dim, entry in entries.items()}
        assert states == {"security": "done", "reliability": "done"}

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
