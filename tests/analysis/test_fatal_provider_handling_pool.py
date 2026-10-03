"""Fatal provider errors abort the run instead of respawning agents: pool, loops and lifecycle."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._loops import interruption_reason, raise_on_fatal_cancel
from quodeq.analysis.cache.failure_streak import CircuitBreakerError
from quodeq.analysis.errors import (
    REASON_AGENT_FAILURE_STREAK, REASON_CANCELLED_SIGNAL, REASON_PROVIDER_FATAL,
    FatalProviderError,
)
from quodeq.analysis.subagents._pool_models import SubagentResult
from quodeq.analysis.subagents._pool_scaling import (
    check_agent_failure_streak,
    should_respawn,
)
from quodeq.analysis.subagents._pool_worker import WorkerContext, run_single_agent
from quodeq.analysis.subprocess import AnalysisConfig
from quodeq.shared import cancellation

from tests._analysis_helpers import _FixedRemainingQueue


class TestSpawnGate:
    def test_should_respawn_returns_zero_when_cancelled(self, tmp_path):
        cancellation.request_cancel()
        assert should_respawn(_FixedRemainingQueue(5), tmp_path / "q.json", 0.0, 0) == 0

    def test_should_respawn_returns_remaining_when_not_cancelled(self, tmp_path):
        assert should_respawn(_FixedRemainingQueue(5), tmp_path / "q.json", 0.0, 0) == 5


def _result(success: bool, error: str = "") -> SubagentResult:
    return SubagentResult(
        agent_id="agent-0", jsonl_file=Path("x.jsonl"),
        stream_file=Path("x.stream"), success=success, error=error,
    )


class TestAgentFailureStreak:
    def test_trips_after_default_streak(self):
        check_agent_failure_streak([_result(False, "boom")] * 5)
        assert cancellation.is_cancelled()
        assert cancellation.cancel_reason() == REASON_AGENT_FAILURE_STREAK

    def test_success_resets_streak(self):
        results = [_result(False)] * 4 + [_result(True)] + [_result(False)] * 4
        check_agent_failure_streak(results)
        assert not cancellation.is_cancelled()

    def test_below_threshold_does_not_trip(self):
        check_agent_failure_streak([_result(False)] * 4)
        assert not cancellation.is_cancelled()

    def test_run_limit_applies(self, monkeypatch):
        # The run's limit arrives resolved; an exported value is not re-read.
        monkeypatch.setenv("QUODEQ_AGENT_FAILURE_STREAK", "50")
        check_agent_failure_streak([_result(False)], limit=2)
        assert not cancellation.is_cancelled()
        check_agent_failure_streak([_result(False)] * 2, limit=2)
        assert cancellation.is_cancelled()

    def test_zero_disables(self):
        check_agent_failure_streak([_result(False)] * 50, limit=0)
        assert not cancellation.is_cancelled()


class TestRunSingleAgentFatal:
    def test_fatal_error_cancels_run_and_returns_failure(self, tmp_path):
        wctx = WorkerContext(
            dimension="security", dimension_key="security",
            evidence_dir=tmp_path, queue_path=tmp_path / "q.json",
        )
        with patch(
            "quodeq.analysis.subagents._pool_worker.run_analysis",
            side_effect=FatalProviderError("quota gone", reason="quota"),
        ):
            result = run_single_agent(0, tmp_path, "prompt", AnalysisConfig(), wctx)
        assert result.success is False
        assert "quota gone" in result.error
        assert cancellation.is_cancelled()
        assert (cancellation.cancel_reason() or "").startswith(f"{REASON_PROVIDER_FATAL}:quota")

    def test_uses_injected_run_fn_instead_of_the_module_default(self, tmp_path):
        """WorkerContext.run_fn is a call-time seam: when set, run_single_agent
        must call it instead of the concrete run_analysis, and never touch the
        module-level default at all."""
        calls: list[dict] = []
        wctx = WorkerContext(
            dimension="security", dimension_key="security",
            evidence_dir=tmp_path, queue_path=tmp_path / "q.json",
            run_fn=lambda **kwargs: calls.append(kwargs),
        )
        with patch(
            "quodeq.analysis.subagents._pool_worker.run_analysis",
            side_effect=AssertionError("the concrete run_analysis must not be called"),
        ):
            result = run_single_agent(0, tmp_path, "prompt", AnalysisConfig(), wctx)
        assert len(calls) == 1
        assert calls[0]["work_dir"] == tmp_path
        assert calls[0]["prompt"] == "prompt"
        assert result.success is True


class TestLoopFatalMapping:
    """interruption_reason (consumer, quodeq.analysis._loop_state) must read back
    exactly what the producers (_pool_worker, _pool_scaling) write via
    cancellation.request_cancel, both sides keyed off quodeq.analysis.errors.REASON_*."""

    def test_interruption_reason_for_fatal_exc(self):
        assert interruption_reason(FatalProviderError("x")) == REASON_PROVIDER_FATAL

    def test_interruption_reason_from_cancel_reason(self):
        cancellation.request_cancel(reason=f"{REASON_PROVIDER_FATAL}:quota: details")
        assert interruption_reason() == REASON_PROVIDER_FATAL

    def test_interruption_reason_streak(self):
        cancellation.request_cancel(reason=REASON_AGENT_FAILURE_STREAK)
        assert interruption_reason() == REASON_AGENT_FAILURE_STREAK

    def test_interruption_reason_plain_cancel(self):
        cancellation.request_cancel()
        assert interruption_reason() == REASON_CANCELLED_SIGNAL

    def test_raise_on_fatal_cancel_raises_fatal(self, tmp_path):
        cancellation.request_cancel(reason=f"{REASON_PROVIDER_FATAL}:quota: credits gone")
        with pytest.raises(FatalProviderError, match="credits gone"):
            raise_on_fatal_cancel(tmp_path)

    def test_raise_on_fatal_cancel_raises_breaker_for_streak(self, tmp_path):
        cancellation.request_cancel(reason=REASON_AGENT_FAILURE_STREAK)
        with pytest.raises(CircuitBreakerError):
            raise_on_fatal_cancel(tmp_path)

    def test_raise_on_fatal_cancel_noop_without_reason(self, tmp_path):
        cancellation.request_cancel()
        raise_on_fatal_cancel(tmp_path)

    def test_raise_on_fatal_cancel_noop_when_not_cancelled(self, tmp_path):
        raise_on_fatal_cancel(tmp_path)

    @staticmethod
    def _write_markers(run_dir, *statuses):
        evidence = run_dir / "evidence"
        evidence.mkdir()
        lines = [
            json.dumps({"_marker": "file_done", "file": f"f{i}.py", "status": s})
            for i, s in enumerate(statuses)
        ]
        (evidence / "security_evidence.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8",
        )

    def test_partial_success_keeps_run_alive(self, tmp_path):
        """Quota died halfway: files were analysed, run finalizes as done."""
        self._write_markers(tmp_path, "ok", "ok", "error")
        cancellation.request_cancel(reason=f"{REASON_PROVIDER_FATAL}:quota: credits gone")
        raise_on_fatal_cancel(tmp_path)  # must not raise

    def test_partial_success_keeps_run_alive_for_streak(self, tmp_path):
        self._write_markers(tmp_path, "ok", "error", "error")
        cancellation.request_cancel(reason=REASON_AGENT_FAILURE_STREAK)
        raise_on_fatal_cancel(tmp_path)  # must not raise

    def test_error_only_markers_still_fail_the_run(self, tmp_path):
        """Markers exist but nothing succeeded: the run produced no analysis."""
        self._write_markers(tmp_path, "error", "error")
        cancellation.request_cancel(reason=f"{REASON_PROVIDER_FATAL}:quota: credits gone")
        with pytest.raises(FatalProviderError):
            raise_on_fatal_cancel(tmp_path)


class TestLifecycleMapping:
    def test_fatal_provider_error_recognised_by_name(self):
        from quodeq.analysis.run_lifecycle import is_named_error
        assert is_named_error(FatalProviderError, "FatalProviderError")
        assert not is_named_error(ValueError, "FatalProviderError")
