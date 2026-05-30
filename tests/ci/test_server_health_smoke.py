"""Boot the Flask API as a real subprocess and assert /api/health serves 200.

Exercises the real socket bind + subprocess spawn cross-platform (the parts a
Flask ``test_client`` cannot cover). This is the headless backend smoke that
gives confidence the server starts on Windows without a desktop session.

Marked ``integration``: it spawns a real process and is timing-sensitive, so it
runs in the dedicated lanes (nightly + windows-integration.yml), not the fast,
deterministic PR gate.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_READY_TIMEOUT_S = 30


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.integration
def test_api_health_subprocess(tmp_path: Path) -> None:
    """The API process starts, binds, and serves GET /api/health -> 200."""
    port = _free_port()
    state = tmp_path / "state"
    env = {
        **os.environ,
        # Isolate the server's real state dir. api.app startup runs
        # sweep_orphaned_clones(), which reads the vars below (falling back to
        # the real ~/.quodeq/*). QUODEQ_HOME is read by nothing, so it does NOT
        # isolate state on its own; point the real keys at tmp_path.
        "QUODEQ_DIR": str(state),
        "QUODEQ_INDEX_DB_PATH": str(state / "index.db"),
        "QUODEQ_EVALUATIONS_DIR": str(state / "evaluations"),
        "QUODEQ_CLONES_DIR": str(state / "clones"),
        "QUODEQ_ACTION_API_HOST": "127.0.0.1",
        "QUODEQ_ACTION_API_PORT": str(port),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "quodeq.api.app"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        url = f"http://127.0.0.1:{port}/api/health"
        deadline = time.monotonic() + _READY_TIMEOUT_S
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                _out, err = proc.communicate()
                pytest.fail(
                    f"API process exited early (rc={proc.returncode}):\n"
                    f"{err.decode('utf-8', 'replace')}"
                )
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
                    body = resp.read().decode("utf-8")
                    assert resp.status == 200, f"status={resp.status} body={body}"
                    assert '"ok"' in body, f"unexpected /api/health body: {body}"
                    return
            except urllib.error.URLError as exc:  # not bound yet -> retry
                last_err = exc
                time.sleep(0.5)
        pytest.fail(
            f"/api/health never returned 200 within {_READY_TIMEOUT_S}s "
            f"(last error: {last_err!r})"
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
