# Run Lifecycle Status — Implementation Plan A (CLI side)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Guarantee every CLI evaluation run leaves an authoritative, explicit terminal state on disk (done / failed / cancelled) regardless of exit mode (normal, exception, SIGINT/TERM/HUP, atexit, heartbeat-detected stale).

**Architecture:** New `status.json` per run (atomic writes via replace), `.heartbeat` file touched every 5s by a background thread, signal handlers for SIGINT/SIGTERM/SIGHUP, atexit fallback, and a try/except wrapper — all wired through a single `RunLifecycleContext` context manager so the CLI body stays clean.

**Tech Stack:** Python 3.12, stdlib only (signal, atexit, threading, json, pathlib). Pytest for tests.

See spec: [2026-04-20-run-lifecycle-status-design.md](2026-04-20-run-lifecycle-status-design.md).

## Scope

This plan ships **Subsystem 1** of the spec: CLI-side lifecycle tracking. After this PR lands, every new run writes `status.json` and `.heartbeat` files with explicit lifecycle transitions. The dashboard keeps reading via today's filesystem scan — it sees the new files (they're ignored, harmless) and behaves identically.

**Plan B (Subsystem 2 — SQLite index + dashboard rerouting + UI badge changes + stale-detection promotion on the dashboard) is a separate follow-up.** That work needs a stable stream of `status.json`-emitting runs to seed its tests, which is why we ship A first.

## Branch Strategy

This plan should be executed on a fresh branch created from `origin/develop` (not on `feat/live-terminal-stream`). Reason: live-terminal-stream is a separate feature. Keep PRs scoped to one concern.

```bash
# From the worktree root:
git fetch origin develop
git checkout -b feat/run-lifecycle-status origin/develop
# Cherry-pick the spec so the branch has its own reference:
git cherry-pick 69dcb097  # the run-lifecycle-status design spec commit
```

If live-terminal-stream has not yet merged, this plan's Task 4 depends on code added by the live-terminal-stream PR (the `RunLogHandler` setup in `_run_pipeline_with_cleanup`). Resolution:

- If live-terminal-stream is merged to develop: proceed as above.
- If not yet merged: branch from `feat/live-terminal-stream` instead and plan to rebase onto develop after live-terminal-stream lands.

## File Structure

**New files (all pure stdlib, no external deps):**
- `src/quodeq/shared/run_status.py` — state machine (enum + allowed transitions), schema, atomic write_status/read_status, TERMINAL_STATES constant.
- `src/quodeq/shared/run_heartbeat.py` — `HeartbeatThread` class (daemon thread, start/stop, swallows OSError).
- `src/quodeq/shared/run_lifecycle.py` — `RunLifecycleContext` context manager that wires status + heartbeat + signal handlers + atexit + exception mapping.
- `tests/shared/test_run_status.py`
- `tests/shared/test_run_heartbeat.py`
- `tests/shared/test_run_lifecycle.py`
- `tests/ci/test_cli_signals.py`

**Modified files:**
- `src/quodeq/_cli_evaluation.py` — `_run_pipeline_with_cleanup` wraps the pipeline body in `with RunLifecycleContext(run_dir, job_id, dimensions): ...` to replace manual state tracking.

## Task 1: `run_status.py` helper module

**Files:**
- Create: `src/quodeq/shared/run_status.py`
- Test: `tests/shared/test_run_status.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/shared/test_run_status.py
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from quodeq.shared.run_status import (
    RunState,
    TERMINAL_STATES,
    UnsupportedSchemaError,
    IllegalTransitionError,
    read_status,
    validate_transition,
    write_status,
)


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    write_status(tmp_path, state=RunState.PENDING, job_id="ext-r", started_at="2026-04-20T00:00:00+00:00", dimensions=["security"])
    status = read_status(tmp_path)
    assert status["state"] == "pending"
    assert status["job_id"] == "ext-r"
    assert status["dimensions"] == ["security"]
    assert status["schema_version"] == 1


def test_atomic_write_uses_tmp_then_rename(tmp_path: Path, monkeypatch) -> None:
    """Readers never see a partial file: write_status must rename a complete tmp."""
    calls: list[str] = []
    real_replace = Path.replace
    def spy_replace(self, target):
        calls.append("replace")
        return real_replace(self, target)
    monkeypatch.setattr(Path, "replace", spy_replace)
    write_status(tmp_path, state=RunState.PENDING, job_id="x", started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    assert calls == ["replace"]
    tmp = tmp_path / "status.json.tmp"
    assert not tmp.exists()
    assert (tmp_path / "status.json").exists()


def test_transition_matrix_legal(tmp_path: Path) -> None:
    for src, dst in [
        (RunState.PENDING, RunState.RUNNING),
        (RunState.RUNNING, RunState.FINALIZING),
        (RunState.FINALIZING, RunState.DONE),
        (RunState.RUNNING, RunState.FAILED),
        (RunState.FINALIZING, RunState.FAILED),
        (RunState.PENDING, RunState.CANCELLED),
        (RunState.RUNNING, RunState.CANCELLED),
        (RunState.FINALIZING, RunState.CANCELLED),
    ]:
        validate_transition(src, dst)  # must not raise


def test_transition_matrix_illegal_raises() -> None:
    for src, dst in [
        (RunState.DONE, RunState.RUNNING),
        (RunState.CANCELLED, RunState.RUNNING),
        (RunState.FAILED, RunState.RUNNING),
        (RunState.PENDING, RunState.FINALIZING),
        (RunState.PENDING, RunState.DONE),
        (RunState.RUNNING, RunState.PENDING),
    ]:
        with pytest.raises(IllegalTransitionError):
            validate_transition(src, dst)


def test_terminal_states() -> None:
    assert TERMINAL_STATES == frozenset({RunState.DONE, RunState.FAILED, RunState.CANCELLED})


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_status(tmp_path) is None


def test_read_corrupt_returns_none(tmp_path: Path) -> None:
    (tmp_path / "status.json").write_text("not-json{")
    assert read_status(tmp_path) is None


def test_read_unsupported_schema_raises(tmp_path: Path) -> None:
    (tmp_path / "status.json").write_text(json.dumps({"schema_version": 99, "state": "running"}))
    with pytest.raises(UnsupportedSchemaError):
        read_status(tmp_path)


def test_concurrent_writes_no_partial_file(tmp_path: Path) -> None:
    """Two threads writing concurrently: each read sees a valid JSON document."""
    barrier = threading.Barrier(2)
    def worker(label: str) -> None:
        barrier.wait()
        for _ in range(50):
            write_status(tmp_path, state=RunState.RUNNING, job_id=label,
                         started_at="2026-04-20T00:00:00+00:00", dimensions=[])
    t1 = threading.Thread(target=worker, args=("A",))
    t2 = threading.Thread(target=worker, args=("B",))
    t1.start(); t2.start(); t1.join(); t2.join()
    # After all writes, the file parses cleanly.
    final = read_status(tmp_path)
    assert final is not None
    assert final["state"] == "running"
    assert final["job_id"] in {"A", "B"}
```

- [ ] **Step 2: Run tests — confirm failure**

```
export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/shared/test_run_status.py -v
```

Expected: ImportError on `quodeq.shared.run_status`.

- [ ] **Step 3: Implement `run_status.py`**

```python
# src/quodeq/shared/run_status.py
"""Authoritative per-run lifecycle state.

Single helper module for reading and writing ``{run_dir}/status.json``. All
state transitions go through ``validate_transition``; hand-rolled JSON is
never written to disk by any other code path.

Failure philosophy: file reads return ``None`` on missing/corrupt; writes
raise only on illegal state transitions or genuine IO errors caller can
propagate.
"""
from __future__ import annotations

import enum
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
STATUS_FILENAME = "status.json"


class RunState(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINALIZING = "finalizing"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATES: frozenset[RunState] = frozenset({RunState.DONE, RunState.FAILED, RunState.CANCELLED})

# Allowed transitions (src -> set of dst). All other transitions raise.
_ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.PENDING: frozenset({RunState.RUNNING, RunState.CANCELLED, RunState.FAILED}),
    RunState.RUNNING: frozenset({RunState.FINALIZING, RunState.CANCELLED, RunState.FAILED}),
    RunState.FINALIZING: frozenset({RunState.DONE, RunState.CANCELLED, RunState.FAILED}),
    # Terminal states accept no further transitions.
    RunState.DONE: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.CANCELLED: frozenset(),
}

_write_lock = threading.Lock()


class IllegalTransitionError(RuntimeError):
    """Raised when a state transition is not permitted by the state machine."""


class UnsupportedSchemaError(RuntimeError):
    """Raised when status.json has a schema_version newer than this code supports."""


def validate_transition(src: RunState, dst: RunState) -> None:
    """Raise IllegalTransitionError if *src → dst* is not permitted."""
    allowed = _ALLOWED_TRANSITIONS.get(src, frozenset())
    if dst not in allowed:
        raise IllegalTransitionError(f"{src.value} → {dst.value} is not a permitted transition")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_status(
    run_dir: Path,
    *,
    state: RunState,
    job_id: str,
    started_at: str,
    dimensions: list[str],
    phase: str | None = None,
    current_dimension: str | None = None,
    pid: int | None = None,
    exit_reason: str | None = None,
    finalized_at: str | None = None,
) -> None:
    """Atomically write status.json with *state* and metadata.

    Uses write-tmp-then-rename so readers never see a partial file.
    Caller is responsible for calling ``validate_transition`` first if a
    transition is being performed.
    """
    if pid is None:
        pid = os.getpid()
    if finalized_at is None and state in TERMINAL_STATES:
        finalized_at = _now_iso()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "state": state.value,
        "started_at": started_at,
        "updated_at": _now_iso(),
        "finalized_at": finalized_at,
        "phase": phase,
        "current_dimension": current_dimension,
        "dimensions": dimensions,
        "pid": pid,
        "exit_reason": exit_reason,
    }
    body = json.dumps(payload, indent=2)
    tmp_path = run_dir / (STATUS_FILENAME + ".tmp")
    final_path = run_dir / STATUS_FILENAME
    with _write_lock:
        tmp_path.write_text(body, encoding="utf-8")
        tmp_path.replace(final_path)


def read_status(run_dir: Path) -> dict[str, Any] | None:
    """Return parsed status.json or None if missing/corrupt.

    Raises UnsupportedSchemaError if the schema_version is newer than this code supports.
    """
    path = run_dir / STATUS_FILENAME
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _logger.warning("corrupt status.json at %s", path)
        return None
    schema = data.get("schema_version", 0)
    if isinstance(schema, int) and schema > SCHEMA_VERSION:
        raise UnsupportedSchemaError(f"status.json schema_version={schema} newer than supported ({SCHEMA_VERSION})")
    return data
```

- [ ] **Step 4: Run tests — confirm pass**

```
uv run pytest tests/shared/test_run_status.py -v
```

Expected: 9 PASS.

- [ ] **Step 5: Commit**

```
git add src/quodeq/shared/run_status.py tests/shared/test_run_status.py
git commit -m "feat(run-status): add RunState, atomic write_status/read_status helper"
```

## Task 2: `run_heartbeat.py` thread module

**Files:**
- Create: `src/quodeq/shared/run_heartbeat.py`
- Test: `tests/shared/test_run_heartbeat.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/shared/test_run_heartbeat.py
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
        time.sleep(0.2)
        second_mtime = (tmp_path / HEARTBEAT_FILENAME).stat().st_mtime
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
    time.sleep(0.2)
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
```

- [ ] **Step 2: Run — confirm failure**

```
uv run pytest tests/shared/test_run_heartbeat.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `run_heartbeat.py`**

```python
# src/quodeq/shared/run_heartbeat.py
"""Per-run heartbeat thread.

Touches ``{run_dir}/.heartbeat`` every *interval* seconds. The file's
mtime is the liveness signal consumed by the dashboard's stale-detection
logic (separate module in Plan B).

Design: daemon thread so a Python interpreter exit during SIGKILL/power-
off does not prevent shutdown.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

_logger = logging.getLogger(__name__)

HEARTBEAT_FILENAME = ".heartbeat"


class HeartbeatThread:
    """Background thread that periodically updates run_dir/.heartbeat mtime."""

    def __init__(self, run_dir: Path, *, interval: float = 5.0) -> None:
        self._path = run_dir / HEARTBEAT_FILENAME
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return  # idempotent
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="quodeq-heartbeat", daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._path.touch()
            except OSError as exc:
                # Best-effort — disk issues surface via other paths.
                _logger.debug("heartbeat touch failed: %s", exc)
            self._stop.wait(self._interval)
```

- [ ] **Step 4: Run — confirm pass**

```
uv run pytest tests/shared/test_run_heartbeat.py -v
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```
git add src/quodeq/shared/run_heartbeat.py tests/shared/test_run_heartbeat.py
git commit -m "feat(run-heartbeat): add HeartbeatThread for liveness signal"
```

## Task 3: `RunLifecycleContext` — signal handlers, atexit, exception wrapper

**Files:**
- Create: `src/quodeq/shared/run_lifecycle.py`
- Test: `tests/shared/test_run_lifecycle.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/shared/test_run_lifecycle.py
from __future__ import annotations

import signal
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.shared.run_status import RunState, read_status
from quodeq.shared.run_lifecycle import RunLifecycleContext


def _ctx(tmp_path: Path) -> RunLifecycleContext:
    return RunLifecycleContext(
        run_dir=tmp_path,
        job_id="ext-test",
        dimensions=["security"],
    )


def test_context_writes_pending_then_running(tmp_path: Path) -> None:
    with _ctx(tmp_path) as ctx:
        status = read_status(tmp_path)
        assert status["state"] == "running"  # transition happened on __enter__
        ctx.transition_to_finalizing()
        assert read_status(tmp_path)["state"] == "finalizing"
    final = read_status(tmp_path)
    assert final["state"] == "done"
    assert final["finalized_at"] is not None


def test_exception_writes_failed(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        with _ctx(tmp_path):
            raise ValueError("boom")
    status = read_status(tmp_path)
    assert status["state"] == "failed"
    assert status["exit_reason"] == "exception: ValueError"


def test_systemexit_treated_as_cancelled(tmp_path: Path) -> None:
    """SystemExit from a signal handler must produce state=cancelled."""
    with pytest.raises(SystemExit):
        with _ctx(tmp_path):
            raise SystemExit(130)
    status = read_status(tmp_path)
    assert status["state"] == "cancelled"


def test_signal_handler_writes_cancelled(tmp_path: Path) -> None:
    """Sending SIGTERM while in context writes cancelled with signal exit_reason."""
    from quodeq.shared.run_lifecycle import RunLifecycleContext

    def send_sigterm_after(delay: float) -> None:
        import time, os
        time.sleep(delay)
        os.kill(os.getpid(), signal.SIGTERM)

    with pytest.raises(SystemExit):
        with RunLifecycleContext(run_dir=tmp_path, job_id="ext-sigterm", dimensions=[]):
            t = threading.Thread(target=send_sigterm_after, args=(0.1,))
            t.start()
            t.join()
            import time; time.sleep(0.3)
    status = read_status(tmp_path)
    assert status["state"] == "cancelled"
    assert status["exit_reason"] == "signal_SIGTERM"


def test_restores_previous_signal_handlers(tmp_path: Path) -> None:
    """After __exit__, signal handlers revert to what they were before __enter__."""
    sentinel = signal.getsignal(signal.SIGINT)
    with _ctx(tmp_path):
        assert signal.getsignal(signal.SIGINT) is not sentinel  # our handler is installed
    assert signal.getsignal(signal.SIGINT) is sentinel


def test_heartbeat_is_touched_during_context(tmp_path: Path) -> None:
    with _ctx(tmp_path):
        import time; time.sleep(0.1)  # allow heartbeat thread to run at least once
        assert (tmp_path / ".heartbeat").exists()


def test_transition_methods(tmp_path: Path) -> None:
    """The context exposes explicit transition methods so callers don't touch status files directly."""
    with _ctx(tmp_path) as ctx:
        ctx.set_phase("analyzing", current_dimension="security")
        status = read_status(tmp_path)
        assert status["phase"] == "analyzing"
        assert status["current_dimension"] == "security"
```

- [ ] **Step 2: Run — confirm failure**

```
uv run pytest tests/shared/test_run_lifecycle.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `run_lifecycle.py`**

```python
# src/quodeq/shared/run_lifecycle.py
"""RunLifecycleContext — unifies status + heartbeat + signal handlers + atexit + exception mapping.

Intended usage:

    with RunLifecycleContext(run_dir, job_id, dimensions) as ctx:
        # Pipeline writes status.json at pending → running automatically.
        do_work()
        ctx.transition_to_finalizing()
        finalize()
    # On normal exit: status.json state=done.
    # On exception:   state=failed (+ exit_reason).
    # On signal:      state=cancelled (+ exit_reason=signal_*).
    # On atexit:      state=cancelled (+ exit_reason=atexit_unfinalized) if still non-terminal.

Signal handlers are restored on __exit__. atexit hook self-deregisters on clean transition out.
"""
from __future__ import annotations

import atexit
import logging
import signal
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import Any

from quodeq.shared.run_heartbeat import HeartbeatThread
from quodeq.shared.run_status import (
    RunState,
    TERMINAL_STATES,
    read_status,
    validate_transition,
    write_status,
)

_logger = logging.getLogger(__name__)

_SIGNALS_TO_HANDLE = (signal.SIGINT, signal.SIGTERM)
# SIGHUP is POSIX-only. Included conditionally below.
if hasattr(signal, "SIGHUP"):
    _SIGNALS_TO_HANDLE = _SIGNALS_TO_HANDLE + (signal.SIGHUP,)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RunLifecycleContext:
    """Context manager bundling lifecycle state + heartbeat + signals + atexit."""

    def __init__(
        self,
        run_dir: Path,
        job_id: str,
        dimensions: list[str],
        *,
        heartbeat_interval: float = 5.0,
    ) -> None:
        self._run_dir = run_dir
        self._job_id = job_id
        self._dimensions = list(dimensions)
        self._started_at = _now_iso()
        self._current_state = RunState.PENDING
        self._phase: str | None = None
        self._current_dimension: str | None = None
        self._heartbeat = HeartbeatThread(run_dir, interval=heartbeat_interval)
        self._previous_handlers: dict[int, Any] = {}
        self._atexit_registered = False

    # ---- Context protocol --------------------------------------------------

    def __enter__(self) -> "RunLifecycleContext":
        self._write(RunState.PENDING)
        self._install_signal_handlers()
        atexit.register(self._finalize_on_atexit)
        self._atexit_registered = True
        self._transition(RunState.RUNNING)
        self._heartbeat.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        self._heartbeat.stop()
        if exc_type is None:
            # No exception — pipeline is expected to have transitioned to finalizing.
            if self._current_state not in TERMINAL_STATES:
                self._transition(RunState.DONE)
        elif issubclass(exc_type, SystemExit):
            # SystemExit raised by our signal handler; state already written there.
            if self._current_state not in TERMINAL_STATES:
                self._transition(RunState.CANCELLED, exit_reason="systemexit")
        else:
            # Any other exception → failed.
            if self._current_state not in TERMINAL_STATES:
                exc_name = exc_type.__name__ if exc_type else "UnknownError"
                self._transition(RunState.FAILED, exit_reason=f"exception: {exc_name}")
        self._restore_signal_handlers()
        self._deregister_atexit()
        return False  # never swallow exceptions

    # ---- Transition API ----------------------------------------------------

    def transition_to_finalizing(self) -> None:
        self._transition(RunState.FINALIZING)

    def set_phase(self, phase: str | None, current_dimension: str | None = None) -> None:
        self._phase = phase
        self._current_dimension = current_dimension
        self._write(self._current_state)

    # ---- Internals ---------------------------------------------------------

    def _transition(self, new_state: RunState, *, exit_reason: str | None = None) -> None:
        validate_transition(self._current_state, new_state)
        self._current_state = new_state
        self._write(new_state, exit_reason=exit_reason)

    def _write(self, state: RunState, *, exit_reason: str | None = None) -> None:
        write_status(
            self._run_dir,
            state=state,
            job_id=self._job_id,
            started_at=self._started_at,
            dimensions=self._dimensions,
            phase=self._phase,
            current_dimension=self._current_dimension,
            exit_reason=exit_reason,
        )

    def _install_signal_handlers(self) -> None:
        def _handle(signum: int, frame: Any) -> None:
            try:
                name = signal.Signals(signum).name
            except ValueError:
                name = f"signal_{signum}"
            # Avoid using the transition-validating path — we may be mid-state.
            self._heartbeat.stop()
            write_status(
                self._run_dir,
                state=RunState.CANCELLED,
                job_id=self._job_id,
                started_at=self._started_at,
                dimensions=self._dimensions,
                phase=self._phase,
                current_dimension=self._current_dimension,
                exit_reason=f"signal_{name}",
            )
            self._current_state = RunState.CANCELLED
            raise SystemExit(128 + signum)

        for sig in _SIGNALS_TO_HANDLE:
            try:
                self._previous_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, _handle)
            except (OSError, ValueError):
                # Can fail in non-main threads; tests may run under such a case.
                pass

    def _restore_signal_handlers(self) -> None:
        for sig, prev in self._previous_handlers.items():
            try:
                signal.signal(sig, prev)
            except (OSError, ValueError):
                pass
        self._previous_handlers.clear()

    def _finalize_on_atexit(self) -> None:
        current = read_status(self._run_dir)
        if current is None:
            return
        state_str = current.get("state")
        if state_str in {s.value for s in TERMINAL_STATES}:
            return
        # We exited without a terminal state — write cancelled.
        self._heartbeat.stop()
        write_status(
            self._run_dir,
            state=RunState.CANCELLED,
            job_id=self._job_id,
            started_at=self._started_at,
            dimensions=self._dimensions,
            phase=self._phase,
            current_dimension=self._current_dimension,
            exit_reason="atexit_unfinalized",
        )

    def _deregister_atexit(self) -> None:
        if not self._atexit_registered:
            return
        try:
            atexit.unregister(self._finalize_on_atexit)
        except Exception:
            pass
        self._atexit_registered = False
```

- [ ] **Step 4: Run — confirm pass**

```
uv run pytest tests/shared/test_run_lifecycle.py -v
```

Expected: 7 PASS. If the signal test hangs or fails because pytest runs in a non-main thread, update the test to use `os.kill(os.getpid(), signal.SIGTERM)` synchronously with the context already entered and simulate the handler being invoked — the plan's test sends from a thread which may not deliver to the main thread on macOS. Acceptable fix: replace the threaded send with a direct call to the installed handler for that test.

- [ ] **Step 5: Commit**

```
git add src/quodeq/shared/run_lifecycle.py tests/shared/test_run_lifecycle.py
git commit -m "feat(run-lifecycle): add RunLifecycleContext bundling status + heartbeat + signals"
```

## Task 4: Integrate `RunLifecycleContext` into `_cli_evaluation.py`

**Files:**
- Modify: `src/quodeq/_cli_evaluation.py` — wrap `_execute_pipeline` call in `_run_pipeline_with_cleanup` with the lifecycle context
- Test: `tests/ci/test_cli_lifecycle_integration.py`

- [ ] **Step 1: Write failing test**

```python
# tests/ci/test_cli_lifecycle_integration.py
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from quodeq.shared.run_status import read_status


def test_pipeline_writes_running_then_done(tmp_path: Path) -> None:
    """On clean exit the pipeline leaves status.json state=done."""
    import quodeq._cli_evaluation as cli

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    with patch.object(cli, "_execute_pipeline", return_value=0), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        import argparse
        args = argparse.Namespace(repo="local")
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()
        cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status is not None, "status.json must be written"
    assert status["state"] == "done"


def test_pipeline_writes_failed_on_exception(tmp_path: Path) -> None:
    """On exception the pipeline leaves status.json state=failed."""
    import quodeq._cli_evaluation as cli

    evidence_dir = tmp_path / "proj" / "run" / "evidence"
    evaluation_dir = tmp_path / "proj" / "run" / "evaluation"
    evidence_dir.mkdir(parents=True)
    evaluation_dir.mkdir(parents=True)

    def _boom(*a, **k):
        raise RuntimeError("pipeline failed")

    import pytest
    with patch.object(cli, "_execute_pipeline", side_effect=_boom), \
         patch.object(cli, "_save_manifest"), \
         patch.object(cli, "_build_run_config"), \
         patch.object(cli, "is_repo_url", return_value=False), \
         patch.object(cli, "emit_marker"):
        import argparse
        args = argparse.Namespace(repo="local")
        inputs = type("I", (), {"src": tmp_path, "language": "python", "manifest": None, "dims_data": None})()
        with pytest.raises(RuntimeError):
            cli._run_pipeline_with_cleanup(args, inputs, (tmp_path, evidence_dir, evaluation_dir))

    run_dir = evaluation_dir.parent
    status = read_status(run_dir)
    assert status["state"] == "failed"
    assert status["exit_reason"] == "exception: RuntimeError"
```

- [ ] **Step 2: Run — confirm failure**

```
uv run pytest tests/ci/test_cli_lifecycle_integration.py -v
```

Expected: FAIL — `status.json` not written because lifecycle not yet wired.

- [ ] **Step 3: Modify `_run_pipeline_with_cleanup`**

Locate the current function body (after the RunLogHandler install added by the live-terminal-stream feature, or equivalent in develop). Wrap the `_execute_pipeline` call in `RunLifecycleContext`.

Expected final structure:

```python
# src/quodeq/_cli_evaluation.py — _run_pipeline_with_cleanup (partial)
from quodeq.shared.run_lifecycle import RunLifecycleContext  # add to imports

def _run_pipeline_with_cleanup(
    args: argparse.Namespace, inputs: ResolvedInputs, paths: tuple[Path, Path, Path],
) -> int:
    _reports_root, evidence_dir, evaluation_dir = paths
    log_info(f"Report path: {evaluation_dir}")
    run_dir = evaluation_dir.parent
    run_id = run_dir.name
    project_uuid = run_dir.parent.name
    emit_marker("report_path", project=project_uuid, runId=run_id)
    _save_manifest(inputs.manifest, evidence_dir)

    pid_file = run_dir / ".pid"
    try:
        pid_file.write_text(str(os.getpid()))
    except OSError:
        pass

    config = _build_run_config(args, inputs=inputs, evidence_dir=evidence_dir)

    # Resolve the selected dimensions list for status.json metadata.
    dimensions_list = getattr(config.options, "dimensions", None) or []

    # Lifecycle context: writes pending → running on enter, done on clean exit,
    # failed on exception, cancelled on signal (SIGINT/SIGTERM/SIGHUP) or atexit.
    with RunLifecycleContext(
        run_dir=run_dir,
        job_id=f"ext-{run_id}",
        dimensions=list(dimensions_list),
    ) as lifecycle:
        try:
            result = _execute_pipeline(args, config, evidence_dir, evaluation_dir)
            lifecycle.transition_to_finalizing()
            return result
        finally:
            try:
                pid_file.unlink(missing_ok=True)
            except OSError:
                pass
            if is_repo_url(args.repo):
                cleanup_cloned_repo(str(inputs.src))
            worktree_dir = getattr(args, "_worktree_dir", None)
            worktree_origin = getattr(args, "_worktree_origin", None)
            if worktree_dir and worktree_origin:
                _cleanup_worktree(worktree_origin, worktree_dir)
```

Keep any existing `RunLogHandler` install from the live-terminal-stream branch (if that branch is merged). It lives outside the lifecycle context and is unrelated.

- [ ] **Step 4: Run — confirm pass**

```
uv run pytest tests/ci/test_cli_lifecycle_integration.py -v
uv run pytest -q
```

Expected: both new tests PASS; full suite green (no regressions in existing CLI tests).

- [ ] **Step 5: Commit**

```
git add src/quodeq/_cli_evaluation.py tests/ci/test_cli_lifecycle_integration.py
git commit -m "feat(cli): wrap pipeline in RunLifecycleContext for guaranteed terminal state"
```

## Task 5: End-to-end signal test via subprocess

**Files:**
- Create: `tests/ci/test_cli_signals.py`

This task verifies that a real subprocess-spawned CLI responds correctly to SIGTERM with a `cancelled` status. This is the critical acceptance test.

- [ ] **Step 1: Write the test**

```python
# tests/ci/test_cli_signals.py
"""End-to-end: real CLI subprocess responds to signals with correct status.json."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.integration
def test_sigterm_writes_cancelled_status(tmp_path: Path) -> None:
    """Spawn CLI via subprocess, send SIGTERM mid-run, assert status.json=cancelled."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "hello.py").write_text("def f(): return 1\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    env = {**os.environ, "QUODEQ_EVALUATIONS_DIR": str(reports)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "quodeq.cli", "evaluate", str(src), "--dry-run", "-d", "security"],
        cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    # Wait for run_dir + status.json to exist.
    run_dir: Path | None = None
    for _ in range(100):
        projects = [d for d in reports.iterdir() if d.is_dir()]
        if projects:
            runs = [d for d in projects[0].iterdir() if d.is_dir()]
            if runs and (runs[0] / "status.json").exists():
                run_dir = runs[0]
                break
        time.sleep(0.1)
    assert run_dir is not None, "CLI did not create status.json in time"

    # Send SIGTERM and wait for exit.
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("CLI did not exit after SIGTERM")

    # Poll briefly for status.json to reflect the terminal write.
    status = None
    for _ in range(20):
        raw = (run_dir / "status.json").read_text()
        data = json.loads(raw)
        if data["state"] in {"cancelled", "done", "failed"}:
            status = data
            break
        time.sleep(0.1)
    assert status is not None
    assert status["state"] == "cancelled"
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
```

- [ ] **Step 2: Run — confirm pass**

```
uv run pytest tests/ci/test_cli_signals.py -v
```

Expected: both PASS within 60s. If the SIGTERM test flakes (signal delivery timing), increase the polling windows — signal reception is not instant on all platforms.

- [ ] **Step 3: Final suite check**

```
uv run pytest -q
```

Expected: fully green.

- [ ] **Step 4: Commit**

```
git add tests/ci/test_cli_signals.py
git commit -m "test(ci): end-to-end CLI signal response writes cancelled status"
```

## Follow-up: Plan B

After this plan ships:

1. Open a follow-up brainstorm for **Plan B** covering SQLite index + dashboard rerouting + `ExternalRunBadge` rename + stale-detection promotion + legacy sync. Dependencies: Plan A merged so new runs emit `status.json` for the DB tests.
2. The spec (2026-04-20-run-lifecycle-status-design.md) already covers Plan B requirements — the follow-up brainstorm can likely skip directly to writing-plans.

## Post-Implementation Verification

Manual checks after all 5 tasks:

1. Run `quodeq evaluate .` normally — check `~/.quodeq/evaluations/.../status.json` reads `state: done`.
2. Start a run, Ctrl+C during analysis — `status.json` reads `state: cancelled`, `exit_reason: signal_SIGINT`.
3. Start a run, `kill` the CLI process from another terminal — `status.json` reads `cancelled`, `exit_reason: signal_SIGTERM`.
4. Start a run, forcibly `kill -9` the CLI process — `status.json` stays `running`; `.heartbeat` mtime freezes. (Dashboard-side stale-detection from Plan B will promote this; for now the file is just stale.)
5. Dashboard still works — old external-run detection (`find_external_runs`) sees the new files, ignores them, continues using manifest/scan presence. No regression.
