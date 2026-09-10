"""Cluster 12 shared regression test: terminal PTY reliability.

Three findings, one causal chain (see .superpowers/sdd/2026-09-09-fault-tolerance-cycle1/
findings/consolidated-tasks.md, Cluster 12):

1. `_pty_windows.py`'s `write()` had no `isalive()` guard (unlike `read()`),
   so a write to a dead process propagated an uncaught exception.
   -> covered directly in tests/terminal/test_pty_windows.py.
2. `_pty_windows.py`'s `kill()` swallowed exceptions with no logger anywhere
   in the file.
   -> also covered in tests/terminal/test_pty_windows.py.
3. `_terminal_ws_helpers.py`'s `terminal_read_loop` swallowed exceptions with
   no log, and -- unlike its write-side counterpart `pump_terminal_out`,
   which unconditionally calls `stop.set()` after its loop -- did not signal
   `stop` on exit. A write exception propagating up through this loop could
   silently end a whole terminal websocket session with the write-side pump
   never told to stop.

This test proves the end-to-end fix for #3, using a fake manager whose
write() raises to stand in for "a write to a dead/killed process mid-session"
(the exact failure mode #1 now prevents at its source -- see
test_pty_windows.py's `test_write_to_dead_process_is_a_noop_not_an_exception`
for that half; this test proves that *if* such a write exception ever
reaches `terminal_read_loop` -- whether from a race, a different backend, or
any other cause -- the loop no longer swallows it silently: it logs, and it
signals `stop` so the concurrently-running write-side pump actually exits
instead of spinning unsignaled forever.
"""
from __future__ import annotations

import logging
import threading
import time

from quodeq.api._terminal_ws_helpers import pump_terminal_out, terminal_read_loop


class _DeadProcessManager:
    """Simulates a PTY whose process died mid-session: reads stay idle
    forever (nothing left to drain), but a write raises -- exactly what an
    unguarded dead-process write does."""

    def __init__(self):
        self.alive = True

    def read(self, max_bytes=65536):
        # Idle forever, like a live-looking PTY with nothing buffered.
        # A short sleep keeps this from hot-spinning the reader thread.
        time.sleep(0.01)
        return ""

    def write(self, data):
        raise RuntimeError("write to dead process")


class _OneShotWriteWs:
    """Delivers exactly one client keystroke frame, then blocks (like a
    real idle websocket) so the read loop's only exit is the exception."""

    def __init__(self):
        self._delivered = False

    def receive(self, timeout=None):
        if not self._delivered:
            self._delivered = True
            return "0x"  # tag "0" (data) -> manager.write(b"x")
        time.sleep(0.05)
        return None


def _unused_apply_control(manager, payload):  # pragma: no cover
    raise AssertionError("apply_control must not run for a data-tagged frame")


def test_dead_process_write_mid_session_logs_and_stops_write_pump(caplog):
    manager = _DeadProcessManager()
    stop = threading.Event()

    # The write-side pump is started first, exactly like terminal_routes.py's
    # `terminal_ws` handler does, so this test proves real concurrent
    # behavior: without the stop-signal fix, this thread would keep polling
    # manager.read() forever (manager.alive stays True) with nothing to ever
    # wake it.
    pump_ws = _OneShotWriteWs()  # unused by the pump; read() never yields data
    reader_thread = threading.Thread(
        target=pump_terminal_out, args=(manager, pump_ws, stop), daemon=True
    )
    reader_thread.start()
    time.sleep(0.05)  # let it actually get into its read loop
    assert reader_thread.is_alive(), "pump should still be running before the write failure"

    with caplog.at_level(logging.WARNING, logger="quodeq.api._terminal_ws_helpers"):
        terminal_read_loop(_OneShotWriteWs(), manager, stop, _unused_apply_control)

    # (a) the read loop logged the failure instead of swallowing it silently.
    assert any(
        r.levelno >= logging.WARNING and "terminal read loop failed" in r.message
        for r in caplog.records
    ), f"expected a logged terminal-read-loop failure, got: {[r.message for r in caplog.records]}"

    # stop must be signaled by terminal_read_loop itself, not merely by
    # whatever wraps it (terminal_routes.py's caller also sets stop in a
    # finally, but this test calls terminal_read_loop directly to prove the
    # function owns this invariant on its own).
    assert stop.is_set(), "terminal_read_loop must signal stop on exit"

    # (b) the write-side pump actually stops -- doesn't spin forever unsignaled.
    reader_thread.join(timeout=2)
    assert not reader_thread.is_alive(), "write pump did not stop after the read loop failed"
