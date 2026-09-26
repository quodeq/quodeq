"""Per-turn cancellation: the signal the stop endpoint uses to end a turn.

A CancelToken is created per in-flight turn (by the /messages route) and
handed down through run_turn into the adapter. Adapters poll `cancelled` at
loop boundaries AND register kill hooks for their blocking externals (the CLI
subprocess, the HTTP client) so cancel() interrupts a stalled read immediately
instead of waiting for the next chunk that may never come.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from quodeq.shared.fault_isolation import run_isolated

_logger = logging.getLogger(__name__)


class TurnCancelled(Exception):
    """The user stopped the turn. Carries any partial answer already streamed
    so the orchestrator can persist what the user actually saw."""

    def __init__(self, partial: str = "") -> None:
        super().__init__("turn stopped")
        self.partial = partial


class CancelToken:
    """One turn's stop signal: a flag adapters poll plus kill hooks that
    interrupt whatever blocking external the turn is parked on."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._kill_hooks: list[Callable[[], None]] = []

    @property
    def cancelled(self) -> bool:
        """True once ``cancel`` has run. Polled at adapter loop boundaries."""
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until cancelled or *timeout* elapses. False on timeout."""
        return self._event.wait(timeout)

    def cancel(self) -> None:
        """Set the flag and run every registered kill hook (once).

        Each hook is its own fault-isolation boundary: a kill hook is a
        third-party/adapter callback (an httpx client's close(), a subprocess
        kill), so a bug in one must not stop the rest from running.
        """
        with self._lock:
            self._event.set()
            hooks, self._kill_hooks = self._kill_hooks, []
        for hook in hooks:
            run_isolated(hook, label="cancel kill hook", log=_logger)

    def register_kill(self, hook: Callable[[], None]) -> None:
        """Run `hook` when cancelled; immediately if already cancelled (a stop
        can land in the window between the route creating the token and the
        adapter spawning its process/client)."""
        with self._lock:
            if not self._event.is_set():
                self._kill_hooks.append(hook)
                return
        _run_late_kill_hook(hook)


def _run_late_kill_hook(hook: Callable[[], None]) -> None:
    """register_kill's late-cancel path: the same fault-isolation boundary
    cancel()'s loop gives every hook, for the one hook that runs immediately
    because the token was already cancelled when it registered."""
    run_isolated(hook, label="cancel kill hook", log=_logger)
