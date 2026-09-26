# src/quodeq/terminal/sessions.py
"""Registry of embedded-terminal sessions.

Each session is one TerminalManager (PTY + scrollback ring + decoder) plus a
per-session single-client lock: two windows must not drain the same PTY, but
two different sessions are independent and may stream concurrently. The
registry is the server-side source of truth for the tab strip — the client
reconciles against ``list()`` rather than persisting its own session list.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass

from quodeq.shared.constants import PLATFORM_WIN32
from quodeq.shared.fault_isolation import run_isolated
from quodeq.terminal.links import child_cwd
from quodeq.terminal.manager import TerminalManager

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TerminalSessionView:
    """Wire-agnostic snapshot of one tab. ``cwd`` is raw (no ``~`` collapse,
    no camelCase) — the route owns that shaping."""

    id: str
    name: str
    alive: bool
    created_at: float
    cwd: str | None


def shell_name() -> str:
    """Display name of the shell the PTY backends will spawn (e.g. "zsh")."""
    if sys.platform == PLATFORM_WIN32:
        from quodeq.terminal._pty_windows import resolve_shell

        path = resolve_shell()
    else:
        from quodeq.terminal._pty_unix import resolve_shell

        path = resolve_shell()[0]
    base = os.path.basename(path)
    return base[:-4] if base.lower().endswith(".exe") else base


class TerminalSession:
    """One tab: a PTY manager, its display name and the lock guarding its
    single WS reader."""

    def __init__(self, sid: str, name: str, manager: TerminalManager, ordinal: int = 0):
        self.id = sid
        self.name = name
        self.ordinal = ordinal
        self.manager = manager
        # One WS client per session (a second reader on the same PTY garbles
        # output); independent sessions each have their own lock.
        self.conn_lock = threading.Lock()
        self.created_at = time.time()

    def to_view(self) -> TerminalSessionView:
        """Snapshot for the tab strip. ``cwd`` is the shell's raw current
        directory (or None when the PTY is gone); the route collapses $HOME
        to ``~`` and builds the camelCase wire keys."""
        return TerminalSessionView(
            id=self.id,
            name=self.name,
            alive=self.manager.alive,
            created_at=self.created_at,
            cwd=child_cwd(self.manager.pid),
        )


class TerminalSessionRegistry:
    """Server-side source of truth for the open terminal tabs.

    Every mutation takes ``_lock``, so create/kill races between the HTTP
    routes and the WS handlers can't leave a half-registered PTY behind.
    """

    MAX_SESSIONS = 6

    def __init__(self, *, manager_factory=TerminalManager):
        self._factory = manager_factory
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    def create(self) -> TerminalSession | None:
        """New session, or None when at MAX_SESSIONS."""
        with self._lock:
            return self._create_locked()

    def _create_locked(self) -> TerminalSession | None:
        if len(self._sessions) >= self.MAX_SESSIONS:
            return None
        # Lowest free ordinal, like real terminal tabs: close "zsh · 2"
        # and the next new session is "zsh · 2" again, so numbers stay
        # within 1..MAX_SESSIONS instead of growing forever.
        used = {s.ordinal for s in self._sessions.values()}
        ordinal = 1
        while ordinal in used:
            ordinal += 1
        sid = uuid.uuid4().hex[:8]
        session = TerminalSession(
            sid, f"{shell_name()} · {ordinal}", self._factory(), ordinal
        )
        self._sessions[sid] = session
        return session

    def get(self, sid: str) -> TerminalSession | None:
        """Look up a session by id. None once it has been killed."""
        with self._lock:
            return self._sessions.get(sid)

    def get_or_create_default(self) -> TerminalSession:
        """First existing session, else a fresh one. Back-compat path for WS
        clients that connect without a session id (pre-multi-session bundles).
        Holds the lock across the check and the create so two concurrent
        callers with no existing session can't each spawn their own PTY."""
        with self._lock:
            for session in self._sessions.values():
                return session
            return self._create_locked() or next(iter(self._sessions.values()))

    def list(self) -> list[TerminalSessionView]:
        """Snapshot every session as a view. The client reconciles its tab
        strip against this instead of keeping its own list."""
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.to_view() for s in sessions]

    def kill(self, sid: str) -> bool:
        """Kill one session's PTY and remove it. False if unknown."""
        with self._lock:
            session = self._sessions.pop(sid, None)
        if session is None:
            return False
        session.manager.kill()
        return True

    def kill_all(self) -> None:
        """Empty the registry and kill every PTY. Called on server shutdown
        so no shell outlives the process. Each kill runs inside its own
        fault-isolation boundary, so one PTY's failed teardown never stops
        the rest from being killed."""
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            run_isolated(session.manager.kill, label=f"terminal session {session.id} kill", log=_logger)

    def pid_for(self, sid: str | None) -> int | None:
        """PID of session ``sid``'s shell, falling back to the first live
        session (for pre-multi-session clients that send no session id)."""
        with self._lock:
            if sid is not None:
                session = self._sessions.get(sid)
                return session.manager.pid if session is not None else None
            for session in self._sessions.values():
                if session.manager.alive:
                    return session.manager.pid
        return None

    @property
    def any_alive(self) -> bool:
        """True while at least one PTY is still running."""
        with self._lock:
            return any(s.manager.alive for s in self._sessions.values())
