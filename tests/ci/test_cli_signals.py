"""End-to-end: real CLI subprocess responds to signals with correct status.json.

Signal-test strategy
--------------------
A ``--dry-run`` evaluation completes in ~15 ms on modern hardware, making it
impossible to reliably send SIGTERM while the process is still alive via
external polling.

We therefore use a thin wrapper script (written to *tmp_path* per-test) that
monkey-patches ``quodeq.analysis._pipeline._run_dry_run`` to sleep for one
second before returning, giving us a reliable window in which to deliver
SIGTERM.  This avoids touching production code while still exercising the
real signal-handling path in ``RunLifecycleContext``.
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WRAPPER_TEMPLATE = textwrap.dedent("""\
    \"\"\"Thin wrapper: patches dry-run to sleep so SIGTERM can interrupt it.\"\"\"
    import sys, time
    from unittest.mock import patch

    # Patch _run_dry_run to sleep for {pause}s before returning, so an
    # external SIGTERM has a reliable window to arrive.
    _orig = None

    def _slow_dry_run(*args, **kwargs):
        import quodeq.analysis._pipeline as _pl
        result = _pl.__dict__["_run_dry_run_orig"](*args, **kwargs)
        time.sleep({pause})
        return result

    import quodeq.analysis._pipeline as _pl
    _pl._run_dry_run_orig = _pl._run_dry_run
    _pl._run_dry_run = _slow_dry_run

    from quodeq.cli import main
    sys.exit(main())
""")


def _write_wrapper(tmp_path: Path, pause: float = 1.0) -> Path:
    """Write a wrapper script that slows the dry-run and return its path."""
    script = tmp_path / "_slow_cli.py"
    script.write_text(_WRAPPER_TEMPLATE.format(pause=pause))
    return script


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_sigterm_writes_cancelled_status(tmp_path: Path) -> None:
    """Spawn CLI subprocess, send SIGTERM mid-run, assert status.json=cancelled."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text("def f(): return 1\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    wrapper = _write_wrapper(tmp_path, pause=1.0)
    env = {**os.environ, "QUODEQ_EVALUATIONS_DIR": str(reports)}

    proc = subprocess.Popen(
        [sys.executable, str(wrapper), "evaluate", str(src), "--dry-run", "-d", "security"],
        cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    # Wait for run_dir + status.json to exist (up to 10 s).
    run_dir: Path | None = None
    for _ in range(200):
        projects = [d for d in reports.iterdir() if d.is_dir()]
        if projects:
            runs = [d for d in projects[0].iterdir() if d.is_dir()]
            if runs and (runs[0] / "status.json").exists():
                run_dir = runs[0]
                break
        time.sleep(0.05)

    if run_dir is None:
        proc.kill()
        proc.wait()
        pytest.fail("CLI did not create status.json within 10 s")

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
