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

_logger = logging.getLogger(__name__)


class TurnCancelled(Exception):
    """The user stopped the turn. Carries any partial answer already streamed
    so the orchestrator can persist what the user actually saw."""

    def __init__(self, partial: str = "") -> None:
        super().__init__("turn stopped")
        self.partial = partial


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._kill_hooks: list[Callable[[], None]] = []

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)

    def cancel(self) -> None:
        """Set the flag and run every registered kill hook (once)."""
        with self._lock:
            self._event.set()
            hooks, self._kill_hooks = self._kill_hooks, []
        for hook in hooks:
            try:
                hook()
            except Exception:  # noqa: BLE001 - kill hooks are best-effort
                _logger.warning("kill hook failed", exc_info=True)

    def register_kill(self, hook: Callable[[], None]) -> None:
        """Run `hook` when cancelled; immediately if already cancelled (a stop
        can land in the window between the route creating the token and the
        adapter spawning its process/client)."""
        with self._lock:
            if not self._event.is_set():
                self._kill_hooks.append(hook)
                return
        try:
            hook()
        except Exception:  # noqa: BLE001 - kill hooks are best-effort
            _logger.warning("kill hook failed", exc_info=True)
