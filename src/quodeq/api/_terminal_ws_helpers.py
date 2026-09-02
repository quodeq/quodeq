"""WebSocket session helpers for the embedded terminal.

Split from terminal_routes.py to keep that file under the size ratchet's
300-line cap. All four functions here were previously either module-level
or nested closures inside ``register_terminal_routes``'s ``terminal_ws``
handler, moved verbatim (only ``_pump_out``/``_terminal_ws`` inner names
renamed to take their captured variables as explicit parameters instead of
closing over them).
"""
from __future__ import annotations

import logging
import os
import threading

from quodeq.terminal.sessions import TerminalSessionRegistry

_logger = logging.getLogger(__name__)

# App-specific WS close codes (4000-4999 range). The client's auto-reconnect
# keys off these: a retry against a held lock or a closed gate can never
# succeed, so it must not loop — only unexpected drops are retried.
WS_CLOSE_NOT_FOUND = 4004  # unknown session id; client reconciles via /sessions


def resolve_ws_session(registry: TerminalSessionRegistry, sid: str | None):
    """Look up (or create) the terminal session for a WS handshake.

    Returns (session, close_code): close_code is None on success; on
    failure session is None and close_code is the WS close code to send.
    """
    if sid:
        session = registry.get(sid)
        if session is None:
            # Stale tab id (e.g. server restarted). The client must not
            # retry this URL — it refetches /sessions and rebuilds tabs.
            return None, WS_CLOSE_NOT_FOUND
        return session, None
    # Pre-multi-session clients connect without an id.
    return registry.get_or_create_default(), None


def pump_terminal_out(manager, ws, stop: threading.Event) -> None:
    while not stop.is_set():
        data = manager.read(65536)
        if not data:
            if not manager.alive:
                break
            continue
        try:
            ws.send("0" + data)
        except Exception:
            break
    stop.set()


def setup_terminal_session(manager, ws) -> bool:
    """Ensure the PTY exists and replay scrollback. Returns False on setup
    failure (already logged)."""
    try:
        manager.ensure_session(cwd=os.path.expanduser("~"), cols=80, rows=24)
        # Replay scrollback so a reattaching client sees recent history.
        # Already text: the manager decodes incrementally, so the ring
        # never holds a torn multi-byte character.
        sb = manager.scrollback()
        if sb:
            ws.send("0" + sb)
        return True
    except Exception:
        # Spawn failure or early disconnect must not propagate past
        # flask-sock (would surface as a 500), but leave a trace for
        # operators — the client only sees a silently closed terminal.
        _logger.warning("terminal session setup failed", exc_info=True)
        return False


def terminal_read_loop(ws, manager, stop: threading.Event, apply_control) -> None:
    try:
        while not stop.is_set():
            msg = ws.receive(timeout=1)
            if msg is None:
                continue
            tag, payload = msg[:1], msg[1:]
            if tag == "0":
                manager.write(payload.encode("utf-8"))
            elif tag == "1":
                apply_control(manager, payload)
    except Exception:
        pass
