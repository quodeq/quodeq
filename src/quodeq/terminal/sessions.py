# src/quodeq/terminal/sessions.py
"""Registry of embedded-terminal sessions.

Each session is one TerminalManager (PTY + scrollback ring + decoder) plus a
per-session single-client lock: two windows must not drain the same PTY, but
two different sessions are independent and may stream concurrently. The
registry is the server-side source of truth for the tab strip — the client
reconciles against ``list()`` rather than persisting its own session list.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid

from quodeq.terminal.links import child_cwd
from quodeq.terminal.manager import TerminalManager


def shell_name() -> str:
    """Display name of the shell the PTY backends will spawn (e.g. "zsh")."""
    if sys.platform == "win32":
        from quodeq.terminal._pty_windows import resolve_shell

        path = resolve_shell()
    else:
        from quodeq.terminal._pty_unix import resolve_shell

        path = resolve_shell()[0]
    base = os.path.basename(path)
    return base[:-4] if base.lower().endswith(".exe") else base


class TerminalSession:
    def __init__(self, sid: str, name: str, manager: TerminalManager, ordinal: int = 0):
        self.id = sid
        self.name = name
        self.ordinal = ordinal
        self.manager = manager
        # One WS client per session (a second reader on the same PTY garbles
        # output); independent sessions each have their own lock.
        self.conn_lock = threading.Lock()
        self.created_at = time.time()

    def to_dict(self) -> dict:
        cwd = child_cwd(self.manager.pid)
        home = os.path.expanduser("~")
        if cwd and home != "~" and (cwd == home or cwd.startswith(home + os.sep)):
            cwd = "~" + cwd[len(home):]
        return {
            "id": self.id,
            "name": self.name,
            "alive": self.manager.alive,
            "createdAt": self.created_at,
            "cwd": cwd,
        }


class TerminalSessionRegistry:
    MAX_SESSIONS = 6

    def __init__(self, *, manager_factory=TerminalManager):
        self._factory = manager_factory
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    def create(self) -> TerminalSession | None:
        """New session, or None when at MAX_SESSIONS."""
        with self._lock:
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
        with self._lock:
            return self._sessions.get(sid)

    def get_or_create_default(self) -> TerminalSession:
        """First existing session, else a fresh one. Back-compat path for WS
        clients that connect without a session id (pre-multi-session bundles)."""
        with self._lock:
            for session in self._sessions.values():
                return session
        return self.create() or next(iter(self._sessions.values()))

    def list(self) -> list[dict]:
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.to_dict() for s in sessions]

    def kill(self, sid: str) -> bool:
        """Kill one session's PTY and remove it. False if unknown."""
        with self._lock:
            session = self._sessions.pop(sid, None)
        if session is None:
            return False
        session.manager.kill()
        return True

    def kill_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            session.manager.kill()

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
        with self._lock:
            return any(s.manager.alive for s in self._sessions.values())
