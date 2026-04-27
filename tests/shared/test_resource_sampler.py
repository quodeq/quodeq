"""Tests for the per-run resource sampler.

The sampler is purely observability — its only job is to never raise
into the lifecycle and to produce a parseable line each tick. We test
the snapshot format, start/stop idempotency, and graceful degradation
when ``ps``/``pgrep`` aren't available (CI sandboxes, weird platforms).
"""
from __future__ import annotations

import re
import time
from unittest.mock import patch

from quodeq.shared.resource_sampler import (
    ResourceSampler,
    _format,
    _ollama_rss_mb,
    _self_rss_mb,
)


class TestSnapshotFormat:
    def test_format_includes_all_fields(self) -> None:
        line = _format(elapsed_s=125, rss_mb=512, threads=8, fds=42, ollama_mb=15384)
        assert line == "[resources] elapsed=2m05s rss=512MB threads=8 fds=42 ollama=15384MB"

    def test_format_handles_zero_elapsed(self) -> None:
        line = _format(elapsed_s=0, rss_mb=0, threads=1, fds=0, ollama_mb=0)
        assert "elapsed=0m00s" in line

    def test_sample_once_matches_format(self) -> None:
        sampler = ResourceSampler()
        sampler.start()
        try:
            line = sampler.sample_once()
        finally:
            sampler.stop()
        # Shape: [resources] elapsed=<m>m<ss>s rss=<n>MB threads=<n> fds=<n> ollama=<n>MB
        assert re.match(
            r"^\[resources\] elapsed=\d+m\d{2}s rss=-?\d+MB threads=\d+ fds=-?\d+ ollama=-?\d+MB$",
            line,
        )


class TestStartStop:
    def test_start_is_idempotent(self) -> None:
        sampler = ResourceSampler(interval_s=999)  # never ticks during test
        sampler.start()
        first = sampler._thread
        sampler.start()  # double-start must not spawn a second thread
        assert sampler._thread is first
        sampler.stop()

    def test_stop_without_start_is_safe(self) -> None:
        ResourceSampler().stop()  # must not raise

    def test_thread_dies_after_stop(self) -> None:
        sampler = ResourceSampler(interval_s=0.05)
        sampler.start()
        thread = sampler._thread
        time.sleep(0.1)  # let it tick at least once
        sampler.stop(timeout=1.0)
        assert thread is not None
        assert not thread.is_alive()


class TestErrorTolerance:
    def test_loop_swallows_log_errors(self) -> None:
        # Observability must never kill the run — even if log_info itself
        # blows up (write to a closed FD, e.g.), the thread keeps going.
        sampler = ResourceSampler(interval_s=0.05)
        with patch(
            "quodeq.shared.resource_sampler.log_info",
            side_effect=OSError("disk full"),
        ):
            sampler.start()
            time.sleep(0.15)  # multiple ticks, each raising
            assert sampler._thread is not None and sampler._thread.is_alive()
            sampler.stop()

    def test_self_rss_returns_int_not_raises(self) -> None:
        # Real ps call against the test process — should always succeed.
        rss = _self_rss_mb()
        assert isinstance(rss, int)
        assert rss > 0  # we exist; we have memory

    def test_self_rss_returns_unknown_when_ps_missing(self) -> None:
        with patch(
            "quodeq.shared.resource_sampler.subprocess.run",
            side_effect=OSError("no ps"),
        ):
            assert _self_rss_mb() == -1

    def test_ollama_rss_returns_zero_when_not_running(self) -> None:
        # pgrep returncode != 0 means not found — distinct from "couldn't ask".
        class _R:
            returncode = 1
            stdout = ""
        with patch(
            "quodeq.shared.resource_sampler.subprocess.run",
            return_value=_R(),
        ):
            assert _ollama_rss_mb() == 0

    def test_ollama_rss_returns_unknown_on_pgrep_error(self) -> None:
        with patch(
            "quodeq.shared.resource_sampler.subprocess.run",
            side_effect=OSError("no pgrep"),
        ):
            assert _ollama_rss_mb() == -1
