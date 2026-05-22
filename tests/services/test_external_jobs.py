"""Tests for the cancel path of external (CLI-started) evaluations."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


def _spawn_test_process(script: str) -> subprocess.Popen:
    """Spawn a Python subprocess running *script* in its own process group."""
    return subprocess.Popen(
        [sys.executable, "-c", script],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _start_reaper(proc: subprocess.Popen) -> threading.Event:
    """Start a daemon thread that reaps *proc* the instant it exits.

    Production runs are reaped by the dashboard's JobManager._monitor_process
    thread (or by whatever shell/launcher parented the CLI). Without an
    equivalent in tests, killed processes linger in zombie state and
    ``os.kill(pid, 0)`` keeps reporting them alive — masking real fixes to
    the cancel path. This emulates the parent-side reaper.
    """
    stop = threading.Event()

    def _reap() -> None:
        while not stop.is_set():
            if proc.poll() is not None:
                return
            time.sleep(0.02)

    threading.Thread(target=_reap, daemon=True).start()
    return stop


def _wait_for_exit(proc: subprocess.Popen, timeout: float) -> bool:
    """Poll proc.poll() up to *timeout* seconds; return True if it exited."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return True
        time.sleep(0.05)
    return False


def _force_cleanup(proc: subprocess.Popen) -> None:
    """Best-effort kill so a failing test doesn't leak a 60s process."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


# ---------------------------------------------------------------------------
# PID resolution
# ---------------------------------------------------------------------------

def test_resolve_external_pid_returns_none_without_pid_file(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    (tmp_path / "proj" / "run").mkdir(parents=True)
    assert resolve_external_pid("proj", "run", tmp_path) is None


def test_resolve_external_pid_returns_pid_when_alive(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text(str(os.getpid()))
    assert resolve_external_pid("proj", "run", tmp_path) == os.getpid()


def test_resolve_external_pid_returns_none_when_process_dead(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    # Use a very high PID that's almost certainly not in use
    (run_dir / ".pid").write_text("999999")
    assert resolve_external_pid("proj", "run", tmp_path) is None


def test_resolve_external_pid_returns_none_for_corrupt_pid_file(tmp_path):
    from quodeq.services._external_jobs import resolve_external_pid

    run_dir = tmp_path / "proj" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / ".pid").write_text("not-a-number")
    assert resolve_external_pid("proj", "run", tmp_path) is None


# ---------------------------------------------------------------------------
# cancel_external_run
# ---------------------------------------------------------------------------

def test_cancel_external_run_returns_false_without_pid_file(tmp_path):
    from quodeq.services._external_jobs import cancel_external_run

    (tmp_path / "proj" / "run").mkdir(parents=True)
    assert cancel_external_run("proj", "run", tmp_path) is False


# ---------------------------------------------------------------------------
# SIGKILL escalation (Bug B regression coverage)
#
# A run process that ignores or is too slow to honor SIGTERM must be reaped
# by an escalated SIGKILL — otherwise the dashboard records `cancelled` while
# the actual process keeps running and racing with future runs. The escalation
# must also reach the process group, not just the captured PID, so children
# spawned by the run (subagent pool, CLI subprocess monitors) die too.
# ---------------------------------------------------------------------------

# Default grace window is short in tests to keep the suite fast. The
# production default lives in _external_jobs.
_TEST_GRACE_S = 0.5


def test_cancel_external_run_escalates_to_sigkill_when_sigterm_ignored(tmp_path):
    """Process that traps and ignores SIGTERM is killed via SIGKILL escalation."""
    from quodeq.services._external_jobs import cancel_external_run

    proc = _spawn_test_process(
        "import signal, time;"
        "signal.signal(signal.SIGTERM, lambda s, f: None);"
        "time.sleep(60)"
    )
    reaper_stop = _start_reaper(proc)
    try:
        run_dir = tmp_path / "proj" / "run"
        run_dir.mkdir(parents=True)
        (run_dir / ".pid").write_text(str(proc.pid))

        # Give the child a moment to install the SIGTERM handler.
        time.sleep(0.2)

        result = cancel_external_run(
            "proj", "run", tmp_path, grace_period_s=_TEST_GRACE_S,
        )

        assert result is True, "cancel should report success after killing the process"
        assert _wait_for_exit(proc, timeout=5.0), (
            "process is still alive after cancel -- SIGKILL escalation missing"
        )
    finally:
        reaper_stop.set()
        _force_cleanup(proc)


def test_cancel_external_run_returns_quickly_when_sigterm_honored(tmp_path):
    """SIGTERM-honoring process is reaped within the grace window without SIGKILL."""
    from quodeq.services._external_jobs import cancel_external_run

    # No SIGTERM handler: Python's default behaviour terminates the process
    # promptly on SIGTERM.
    proc = _spawn_test_process("import time; time.sleep(60)")
    reaper_stop = _start_reaper(proc)
    try:
        run_dir = tmp_path / "proj" / "run"
        run_dir.mkdir(parents=True)
        (run_dir / ".pid").write_text(str(proc.pid))

        time.sleep(0.2)

        start = time.monotonic()
        result = cancel_external_run(
            "proj", "run", tmp_path, grace_period_s=2.0,
        )
        elapsed = time.monotonic() - start

        assert result is True
        assert _wait_for_exit(proc, timeout=2.0)
        # The grace window is 2s; a SIGTERM-honoring process should die well
        # under that and cancel should return without waiting the full window.
        assert elapsed < 1.5, (
            f"cancel took {elapsed:.2f}s for a SIGTERM-honoring process -- "
            f"the grace window should not be waited out unnecessarily"
        )
    finally:
        reaper_stop.set()
        _force_cleanup(proc)


def test_cancel_external_run_kills_child_processes_in_same_group(tmp_path):
    """A run that has spawned a child subprocess must take the child down too.

    The real failure mode: the CLI parent honored SIGTERM and exited, but
    a subagent child still has a hung Ollama request and lives on, holding
    file locks and racing the next run. The cancel path must kill the group.
    """
    from quodeq.services._external_jobs import cancel_external_run

    # Parent process spawns a long-sleeping child in the same session.
    # We print the child PID then sleep so the test can poll the child too.
    script = (
        "import os, sys, signal, subprocess, time;"
        "signal.signal(signal.SIGTERM, lambda s, f: None);"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        "open('"
        + str(tmp_path / "child.pid")
        + "', 'w').write(str(child.pid));"
        "time.sleep(60)"
    )
    proc = _spawn_test_process(script)
    reaper_stop = _start_reaper(proc)
    try:
        run_dir = tmp_path / "proj" / "run"
        run_dir.mkdir(parents=True)
        (run_dir / ".pid").write_text(str(proc.pid))

        # Wait for the child PID file to appear.
        child_pid_file = tmp_path / "child.pid"
        for _ in range(50):
            if child_pid_file.exists():
                break
            time.sleep(0.05)
        assert child_pid_file.exists(), "test setup: child never wrote its PID"
        child_pid = int(child_pid_file.read_text())

        cancel_external_run(
            "proj", "run", tmp_path, grace_period_s=_TEST_GRACE_S,
        )

        # Both parent and child must be gone.
        assert _wait_for_exit(proc, timeout=5.0), "parent still alive after cancel"
        deadline = time.monotonic() + 5.0
        child_dead = False
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                child_dead = True
                break
            time.sleep(0.05)
        assert child_dead, (
            f"child pid {child_pid} survived parent cancel -- process-group kill missing"
        )
    finally:
        reaper_stop.set()
        _force_cleanup(proc)
