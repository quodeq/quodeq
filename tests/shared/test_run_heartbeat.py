from __future__ import annotations

import time
from pathlib import Path

import pytest

from quodeq.shared.run_heartbeat import HeartbeatThread, HEARTBEAT_FILENAME


def test_starts_and_touches_file(tmp_path: Path) -> None:
    hb = HeartbeatThread(tmp_path, interval=0.05)
    hb.start()
    try:
        time.sleep(0.2)
        assert (tmp_path / HEARTBEAT_FILENAME).exists()
        first_mtime = (tmp_path / HEARTBEAT_FILENAME).stat().st_mtime
        # Poll for the next touch instead of a fixed sleep: a loaded CI runner
        # can starve the heartbeat thread so no touch lands inside a 0.2s
        # window, leaving both reads on the same mtime (a false failure). This
        # mirrors the deadline-poll pattern in test_swallows_oserror below.
        second_mtime = first_mtime
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            second_mtime = (tmp_path / HEARTBEAT_FILENAME).stat().st_mtime
            if second_mtime > first_mtime:
                break
            time.sleep(0.02)
        assert second_mtime > first_mtime, "heartbeat should advance mtime between intervals"
    finally:
        hb.stop()


def test_stop_ceases_touches(tmp_path: Path) -> None:
    hb = HeartbeatThread(tmp_path, interval=0.05)
    hb.start()
    time.sleep(0.1)
    hb.stop()
    mtime_at_stop = (tmp_path / HEARTBEAT_FILENAME).stat().st_mtime
    time.sleep(0.2)
    # File should not be touched after stop.
    assert (tmp_path / HEARTBEAT_FILENAME).stat().st_mtime == mtime_at_stop


def test_swallows_oserror(tmp_path: Path, monkeypatch) -> None:
    """OSError during touch must not kill the thread."""
    errors: list[int] = []
    real_touch = Path.touch
    def raising_touch(self, *args, **kwargs):
        errors.append(1)
        if len(errors) <= 2:
            raise OSError("simulated disk full")
        return real_touch(self, *args, **kwargs)
    monkeypatch.setattr(Path, "touch", raising_touch)
    hb = HeartbeatThread(tmp_path, interval=0.02)
    hb.start()
    # Poll instead of sleeping a fixed window — a loaded CI runner can
    # tick the heartbeat much slower than 20 ms, so a 200 ms sleep is
    # not enough headroom to guarantee >=3 touches.
    deadline = time.monotonic() + 5.0
    while len(errors) < 3 and time.monotonic() < deadline:
        time.sleep(0.05)
    hb.stop()
    # After the simulated failures, touches eventually succeeded.
    assert len(errors) >= 3


def test_double_start_is_noop(tmp_path: Path) -> None:
    hb = HeartbeatThread(tmp_path, interval=0.1)
    hb.start()
    hb.start()  # must not raise, must not spawn a second thread
    hb.stop()


def test_stop_without_start_is_safe(tmp_path: Path) -> None:
    HeartbeatThread(tmp_path, interval=1.0).stop()  # must not raise
