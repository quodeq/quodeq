"""End-to-end: real CLI subprocess responds to signals with correct status.json.

Signal-test strategy
--------------------
A ``--dry-run`` evaluation completes in ~15 ms on modern hardware, making it
impossible to reliably send SIGTERM while the process is still alive via
external polling.

We therefore use a thin wrapper script (written to *tmp_path* per-test) that
monkey-patches ``quodeq.analysis._pipeline._run_dry_run`` to write a ready
marker and then sleep before returning. The test waits for the marker — not
merely for status.json to exist — which guarantees the child is inside the
interruptible pause with the lifecycle signal handlers installed before
SIGTERM is sent. The pause is generous (tens of seconds) because SIGTERM cuts
it short; it is a ceiling, not a duration. This avoids touching production
code while still exercising the real signal-handling path in
``RunLifecycleContext``.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

# Subprocess waits up to 120 s inside these tests; give pytest-timeout
# enough room above that to avoid double-killing a still-cleaning-up
# process.
pytestmark = pytest.mark.timeout(180)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WRAPPER_TEMPLATE = textwrap.dedent("""\
    \"\"\"Thin wrapper: patches dry-run to pause so SIGTERM can interrupt it.\"\"\"
    import sys, time
    from pathlib import Path

    def _slow_dry_run(*args, **kwargs):
        import quodeq.analysis._pipeline as _pl
        result = _pl.__dict__["_run_dry_run_orig"](*args, **kwargs)
        # Handshake: tell the test we are mid-run with the lifecycle signal
        # handlers live, then linger in an interruptible sleep. SIGTERM cuts
        # the sleep short, so {pause}s is a ceiling, not a duration — it is
        # only waited out if signal delivery fails entirely.
        Path({marker!r}).touch()
        time.sleep({pause})
        return result

    import quodeq.analysis._pipeline as _pl
    _pl._run_dry_run_orig = _pl._run_dry_run
    _pl._run_dry_run = _slow_dry_run

    from quodeq.cli import main
    sys.exit(main())
""")


def _write_wrapper(tmp_path: Path, marker: Path, pause: float = 45.0) -> Path:
    """Write a wrapper script that pauses the dry-run and return its path."""
    script = tmp_path / "_slow_cli.py"
    script.write_text(_WRAPPER_TEMPLATE.format(marker=str(marker), pause=pause))
    return script


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows TerminateProcess (what send_signal(SIGTERM) maps to) is not "
    "catchable, so the SIGTERM handler that writes the cancelled status never "
    "runs. Windows cancellation uses CTRL_BREAK_EVENT, which the CLI lifecycle "
    "does not yet handle; a Windows-specific cancellation test is a separate "
    "follow-up.",
)
def test_sigterm_writes_cancelled_status(tmp_path: Path) -> None:
    """Spawn CLI subprocess, send SIGTERM mid-run, assert status.json=cancelled.

    POSIX-only: see the skipif above for why this cannot run on Windows.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text("def f(): return 1\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    marker = tmp_path / "sigterm_ready"
    wrapper = _write_wrapper(tmp_path, marker)
    env = {**os.environ, "QUODEQ_EVALUATIONS_DIR": str(reports)}

    proc = subprocess.Popen(
        [sys.executable, str(wrapper), "evaluate", str(src), "--dry-run", "-d", "security"],
        cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    # Wait for the handshake marker: it is written from inside the paused
    # dry-run, so once it exists the child is guaranteed to be inside the
    # lifecycle context with signal handlers installed and the run_dir
    # (including status.json) already on disk.
    deadline = time.monotonic() + 60
    while not marker.exists():
        if proc.poll() is not None:
            _out, err = proc.communicate()
            pytest.fail(f"CLI exited before reaching the dry-run pause: {err.decode()}")
        if time.monotonic() > deadline:
            proc.kill()
            proc.wait()
            pytest.fail("CLI did not reach the dry-run pause within 60 s")
        time.sleep(0.05)

    projects = [d for d in reports.iterdir() if d.is_dir()]
    runs = [d for d in projects[0].iterdir() if d.is_dir()] if projects else []
    if not runs or not (runs[0] / "status.json").exists():
        proc.kill()
        proc.wait()
        pytest.fail("run_dir/status.json missing even though the dry-run pause was reached")
    run_dir = runs[0]

    # Send SIGTERM and wait for process to exit.
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("CLI did not exit after SIGTERM within 30 s")

    # Poll for the terminal state to be written.
    status = None
    for _ in range(40):
        try:
            data = json.loads((run_dir / "status.json").read_text())
            if data["state"] in {"cancelled", "done", "failed"}:
                status = data
                break
        except (json.JSONDecodeError, OSError):
            pass
        time.sleep(0.1)

    assert status is not None, "status.json never reached a terminal state"
    assert status["state"] == "cancelled", (
        f"Expected 'cancelled', got '{status['state']}' "
        f"(exit_reason={status.get('exit_reason')!r})"
    )
    assert status["exit_reason"] == "signal_SIGTERM"


@pytest.mark.integration
def test_normal_completion_writes_done(tmp_path: Path) -> None:
    """A complete dry-run exits with status.json=done."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text("def f(): return 1\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    env = {**os.environ, "QUODEQ_EVALUATIONS_DIR": str(reports)}
    proc = subprocess.run(
        [sys.executable, "-m", "quodeq.cli", "evaluate", str(src), "--dry-run", "-d", "security"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"CLI failed: {proc.stderr}"

    projects = [d for d in reports.iterdir() if d.is_dir()]
    runs = [d for d in projects[0].iterdir() if d.is_dir()]
    run_dir = runs[0]
    status = json.loads((run_dir / "status.json").read_text())
    assert status["state"] == "done"
    assert status["exit_reason"] is None
