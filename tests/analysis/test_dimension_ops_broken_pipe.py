"""BrokenPipeError on the success-log line must not mark a successful dim as incomplete.

Regression: the dashboard's stdout pipe can close at any moment (parent
restarting, kernel pipe-buffer pressure, etc.). When that happens between
the dim's dispatch finishing and the success log line being written, the
log call raises BrokenPipeError. Pre-fix, this propagated out of
``_process_single_dimension`` and the loop's outer except branch caught
it as if the dim itself had failed -- writing INCOMPLETE state, skipping
``_score_dimension``, and erasing the dim from the run report despite
the JSONL having all the findings on disk.

Observed in the wild on a 3-dim run: flexibility ran clean (18 files,
22v/1c), but the success log raised BrokenPipeError, and the run report
showed only 2 dims (maintainability + performance) with 80 violations
instead of the actual 113.

The fix: ``_process_single_dimension`` swallows BrokenPipeError around
the success-log call so a logging failure doesn't mask a successful
analysis. Stdout/stderr are then redirected to /dev/null so the rest of
the run can keep logging without compounding the error.
"""
from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._dimension_ops import _process_single_dimension
from quodeq.core.evidence.model import Evidence


def _make_evidence() -> Evidence:
    return Evidence(
        repository="", language="python", date="2026-01-01",
        source_file_count=18, files_read=18, coverage_pct=100.0, principles={},
    )


def _make_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.total = 3
    return ctx


class TestSuccessLogBrokenPipe:
    def test_returns_evidence_when_log_raises(self):
        """If _log_dimension_result raises BrokenPipeError, the function
        still returns the Evidence. The dim is analytically successful;
        a logging failure must not mask that."""
        ev = _make_evidence()
        with patch(
            "quodeq.analysis._dimension_ops.process_dimension_with_cache",
            return_value=ev,
        ), patch(
            "quodeq.analysis._dimension_ops._log_dimension_result",
            side_effect=BrokenPipeError("dashboard pipe closed"),
        ), patch(
            "quodeq.analysis._loops._silence_broken_stdout",
        ) as mock_silence:
            result = _process_single_dimension(
                MagicMock(), "flexibility", 3, _make_ctx(), emit_log=True,
            )
        assert result is ev, (
            "BrokenPipeError on success-log must not propagate; the dim's "
            "Evidence must still be returned to the caller"
        )
        mock_silence.assert_called_once()

    def test_no_silence_when_log_succeeds(self):
        """Sanity: the silence-stdout fallback only fires when logging
        actually fails. Normal runs should not hit the BrokenPipeError
        recovery path."""
        ev = _make_evidence()
        with patch(
            "quodeq.analysis._dimension_ops.process_dimension_with_cache",
            return_value=ev,
        ), patch(
            "quodeq.analysis._dimension_ops._log_dimension_result",
        ), patch(
            "quodeq.analysis._loops._silence_broken_stdout",
        ) as mock_silence:
            result = _process_single_dimension(
                MagicMock(), "flexibility", 3, _make_ctx(), emit_log=True,
            )
        assert result is ev
        mock_silence.assert_not_called()

    def test_emit_log_false_skips_log_entirely(self):
        """When emit_log=False (incremental fallback path), the success
        log isn't called at all -- so the BrokenPipeError fallback must
        not run either, and the original behaviour is unchanged."""
        ev = _make_evidence()
        with patch(
            "quodeq.analysis._dimension_ops.process_dimension_with_cache",
            return_value=ev,
        ), patch(
            "quodeq.analysis._dimension_ops._log_dimension_result",
        ) as mock_log, patch(
            "quodeq.analysis._loops._silence_broken_stdout",
        ) as mock_silence:
            result = _process_single_dimension(
                MagicMock(), "flexibility", 3, _make_ctx(), emit_log=False,
            )
        assert result is ev
        mock_log.assert_not_called()
        mock_silence.assert_not_called()

    def test_other_exceptions_still_propagate(self):
        """A non-BrokenPipe exception in _log_dimension_result is a real
        bug and must still propagate -- we're only swallowing the specific
        BrokenPipeError case where the analysis itself succeeded."""
        ev = _make_evidence()
        with patch(
            "quodeq.analysis._dimension_ops.process_dimension_with_cache",
            return_value=ev,
        ), patch(
            "quodeq.analysis._dimension_ops._log_dimension_result",
            side_effect=RuntimeError("real bug"),
        ):
            with pytest.raises(RuntimeError, match="real bug"):
                _process_single_dimension(
                    MagicMock(), "flexibility", 3, _make_ctx(), emit_log=True,
                )
