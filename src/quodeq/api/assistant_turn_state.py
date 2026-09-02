"""Per-app assistant turn/SSE-stream registry.

Split out of assistant_routes.py (Task 10): the ``AssistantTurnState`` class
and the request-context shims the workspace routes use to claim/release the
same per-session turn slot as a /messages turn.
"""
from __future__ import annotations

import threading

from flask import Flask, current_app

from quodeq.assistant.cancel import CancelToken

# Each open assistant SSE stream pins a server worker thread for its whole
# lifetime, and the global rate limiter exempts GETs — without a cap an
# authenticated caller can exhaust every worker with idle streams. 16 is
# generous for the real UI (one stream per open drawer/tab).
_MAX_SSE_STREAMS = 16


class AssistantTurnState:
    """Per-app registry of running turns, cancel tokens, and open SSE streams.

    One instance per Flask app (``app.extensions["assistant_turns"]``,
    created in ``create_app``) so two apps in one process — or two tests —
    never share turn slots. Lock granularity matches the former module
    globals: one lock guards the turn/token registry, another the SSE
    stream counter.
    """

    def __init__(self, max_sse_streams: int = _MAX_SSE_STREAMS) -> None:
        self._running_turns: set[str] = set()
        # Cancel token per session with a /messages turn in flight; the /stop
        # route fires it. Workspace actions (apply/pr) claim the turn slot too
        # but are not stoppable, so they never appear here.
        self._cancel_tokens: dict[str, CancelToken] = {}
        self._running_lock = threading.Lock()
        self._max_sse_streams = max_sse_streams
        self._open_sse_streams = 0
        self._sse_lock = threading.Lock()

    def try_claim_turn(self, sid: str) -> bool:
        """Atomically claim the per-session turn slot for a workspace action
        so a concurrent /messages turn (or another apply/pr) 409s instead of
        racing the same worktree. Returns False if already claimed."""
        with self._running_lock:
            if sid in self._running_turns:
                return False
            self._running_turns.add(sid)
            return True

    def claim_turn(self, sid: str) -> CancelToken | None:
        """Claim the turn slot for a /messages turn and mint its cancel token
        in one atomic step. Returns None when the slot is already claimed."""
        with self._running_lock:
            if sid in self._running_turns:
                return None
            self._running_turns.add(sid)
            token = self._cancel_tokens[sid] = CancelToken()
            return token

    def release_turn(self, sid: str) -> None:
        """Free the per-session turn slot and drop the turn's cancel token.

        Workspace actions never register a token, so the pop is a no-op for
        them; the slot is exclusive, so it can only ever drop this turn's own
        token."""
        with self._running_lock:
            self._running_turns.discard(sid)
            self._cancel_tokens.pop(sid, None)

    def is_turn_claimed(self, sid: str) -> bool:
        with self._running_lock:
            return sid in self._running_turns

    def cancel_token(self, sid: str) -> CancelToken | None:
        with self._running_lock:
            return self._cancel_tokens.get(sid)

    def try_open_sse_stream(self) -> bool:
        """Take one SSE slot; False when the cap is reached (caller 429s)."""
        with self._sse_lock:
            if self._open_sse_streams >= self._max_sse_streams:
                return False
            self._open_sse_streams += 1
            return True

    def close_sse_stream(self) -> None:
        with self._sse_lock:
            self._open_sse_streams -= 1

    @property
    def open_sse_streams(self) -> int:
        with self._sse_lock:
            return self._open_sse_streams


def _turn_state(app: Flask) -> AssistantTurnState:
    """The app's turn registry. ``create_app`` instantiates it; setdefault
    keeps bare test apps (register_assistant_routes on a plain Flask) working."""
    return app.extensions.setdefault("assistant_turns", AssistantTurnState())


def _try_claim_turn(sid: str) -> bool:
    """Request-context shim for the workspace routes (see AssistantTurnState)."""
    return _turn_state(current_app).try_claim_turn(sid)


def _release_turn(sid: str) -> None:
    """Request-context shim for the workspace routes (see AssistantTurnState)."""
    _turn_state(current_app).release_turn(sid)
