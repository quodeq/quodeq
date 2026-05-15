"""DimensionRunner — tests via injected callbacks, no real AI needed.

The seam is DimensionRunner(callbacks=...).run(config, dim_id, idx, ctx).
Callbacks replace the three AI steps (prompt build, dispatch, parse)
so every orchestration behaviour is testable without infrastructure.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis.dimension_runner import DimensionRunner
from quodeq.analysis.subagents.runner import DimensionCallbacks
from quodeq.core.evidence.model import Evidence


def _make_evidence(**kwargs) -> Evidence:
    defaults = dict(
        repository="", language="python", date="2026-01-01",
        source_file_count=5, files_read=5, coverage_pct=100.0, principles={},
    )
    return Evidence(**{**defaults, **kwargs})


def _make_ctx(total: int = 3) -> MagicMock:
    ctx = MagicMock()
    ctx.total = total
    return ctx


def _noop_callbacks(evidence: Evidence | None) -> DimensionCallbacks:
    """Return callbacks that short-circuit dispatch and return *evidence*."""
    return DimensionCallbacks(
        build_prompt=lambda *a, **kw: "prompt",
        run_analysis=lambda *a, **kw: (MagicMock(), MagicMock()),
        parse_evidence=lambda *a, **kw: evidence,
    )


# ---------------------------------------------------------------------------
# Core contract
# ---------------------------------------------------------------------------

class TestDimensionRunnerContract:
    def test_returns_evidence_on_success(self):
        ev = _make_evidence()
        with patch(
            "quodeq.analysis.dimension_runner.process_dimension_with_cache",
            return_value=ev,
        ):
            result = DimensionRunner().run(MagicMock(), "security", 1, _make_ctx())
        assert result is ev

    def test_returns_none_when_cache_returns_none(self):
        with patch(
            "quodeq.analysis.dimension_runner.process_dimension_with_cache",
            return_value=None,
        ):
            result = DimensionRunner().run(MagicMock(), "security", 1, _make_ctx())
        assert result is None

    def test_passes_injected_callbacks_to_cache_runner(self):
        ev = _make_evidence()
        callbacks = _noop_callbacks(ev)
        captured = {}

        def fake_cache(config, dim_id, idx, ctx, cbs, **kw):
            captured["callbacks"] = cbs
            return ev

        with patch(
            "quodeq.analysis.dimension_runner.process_dimension_with_cache",
            side_effect=fake_cache,
        ):
            DimensionRunner(callbacks=callbacks).run(MagicMock(), "security", 1, _make_ctx())

        assert captured["callbacks"] is callbacks


# ---------------------------------------------------------------------------
# BrokenPipeError guard on success log
# ---------------------------------------------------------------------------

class TestBrokenPipeGuard:
    def test_returns_evidence_when_success_log_raises(self):
        ev = _make_evidence()
        with patch(
            "quodeq.analysis.dimension_runner.process_dimension_with_cache",
            return_value=ev,
        ), patch(
            "quodeq.analysis.dimension_runner._log_dimension_result",
            side_effect=BrokenPipeError("pipe closed"),
        ), patch(
            "quodeq.analysis._loops._silence_broken_stdout",
        ) as mock_silence:
            result = DimensionRunner().run(
                MagicMock(), "flexibility", 3, _make_ctx(), emit_log=True,
            )

        assert result is ev
        mock_silence.assert_called_once()

    def test_non_broken_pipe_still_propagates(self):
        ev = _make_evidence()
        with patch(
            "quodeq.analysis.dimension_runner.process_dimension_with_cache",
            return_value=ev,
        ), patch(
            "quodeq.analysis.dimension_runner._log_dimension_result",
            side_effect=RuntimeError("real bug"),
        ):
            with pytest.raises(RuntimeError, match="real bug"):
                DimensionRunner().run(
                    MagicMock(), "flexibility", 1, _make_ctx(), emit_log=True,
                )


# ---------------------------------------------------------------------------
# emit_log=False path (incremental)
# ---------------------------------------------------------------------------

class TestEmitLog:
    def test_emit_log_false_skips_log_entirely(self):
        ev = _make_evidence()
        with patch(
            "quodeq.analysis.dimension_runner.process_dimension_with_cache",
            return_value=ev,
        ), patch(
            "quodeq.analysis.dimension_runner._log_dimension_result",
        ) as mock_log, patch(
            "quodeq.analysis.dimension_runner.emit_marker",
        ) as mock_marker:
            result = DimensionRunner().run(
                MagicMock(), "security", 1, _make_ctx(), emit_log=False,
            )

        assert result is ev
        mock_log.assert_not_called()
        mock_marker.assert_not_called()

    def test_emit_log_true_emits_analyzing_marker(self):
        ev = _make_evidence()
        with patch(
            "quodeq.analysis.dimension_runner.process_dimension_with_cache",
            return_value=ev,
        ), patch(
            "quodeq.analysis.dimension_runner._log_dimension_result",
        ), patch(
            "quodeq.analysis.dimension_runner.emit_marker",
        ) as mock_marker:
            DimensionRunner().run(
                MagicMock(), "security", 1, _make_ctx(), emit_log=True,
            )

        mock_marker.assert_any_call("analyzing", dimension="security")
