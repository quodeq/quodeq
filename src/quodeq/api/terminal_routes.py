"""WebSocket + control routes for the embedded terminal.

The WS handshake is a GET, which api/security.py's CSRF hook exempts, so this
module enforces the Origin check itself via terminal_gate_reason."""
from __future__ import annotations

import atexit
import json
import logging
import os
import struct
import subprocess
import threading

from flask import Flask, current_app, jsonify, request
from flask_sock import Sock

from quodeq.api._terminal_ws_helpers import (
    pump_terminal_out,
    resolve_ws_session,
    setup_terminal_session,
    terminal_read_loop,
)
from quodeq.terminal.gate import terminal_env_reason, terminal_gate_reason
from quodeq.terminal.links import (
    build_open_argv,
    detect_editor,
    resolve_bases,
    resolve_path,
    safe_editor_path,
)
from quodeq.terminal.sessions import TerminalSessionRegistry, shell_name

_logger = logging.getLogger(__name__)


def _env_reason() -> str | None:
    # Environment availability only (no Origin) — for /status, a same-origin
    # GET the browser sends WITHOUT an Origin header. Gating it on Origin would
    # wrongly report the terminal disabled ("Missing Origin header").
    return terminal_env_reason(
        host=current_app.config.get("QUODEQ_BIND_HOST", ""),
        api_key=current_app.config.get("QUODEQ_API_KEY"),
        request_host=request.host,
    )


def _gate_reason() -> str | None:
    # Full gate incl. Origin — for the WS handshake (browsers DO send Origin on
    # WS) and the /kill POST (Origin also enforced by the global CSRF hook).
    return terminal_gate_reason(
        host=current_app.config.get("QUODEQ_BIND_HOST", ""),
        api_key=current_app.config.get("QUODEQ_API_KEY"),
        origin=request.headers.get("Origin"),
        request_host=request.host,
    )


# App-specific WS close codes (4000-4999 range). The client's auto-reconnect
# keys off these: a retry against a held lock or a closed gate can never
# succeed, so it must not loop — only unexpected drops are retried.
_WS_CLOSE_BUSY = 4002      # per-session connection lock held by another window
_WS_CLOSE_REFUSED = 4003   # terminal gate refused the handshake
# 4004 (unknown session id) lives in _terminal_ws_helpers.WS_CLOSE_NOT_FOUND —
# it's returned from resolve_ws_session, not referenced directly here.


def _coerce_int(value) -> int | None:
    """Line/col from a JSON body: accept ints or numeric strings, else None."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _clamp_winsize(value: int) -> int:
    """Keep a terminal dimension within struct.pack('HH') range (1..65535)."""
    return max(1, min(int(value), 65535))


def _apply_control(manager, payload: str) -> None:
    """Apply a control frame's resize; ignore malformed input (never raise).

    Out-of-range dimensions are clamped (not dropped) so a stray huge/negative
    value keeps the terminal usable instead of crashing struct.pack in the PTY.
    """
    try:
        ctrl = json.loads(payload)
        rs = ctrl.get("resize") if isinstance(ctrl, dict) else None
        if rs:
            manager.resize(_clamp_winsize(rs["cols"]), _clamp_winsize(rs["rows"]))
    except (ValueError, KeyError, TypeError, struct.error):
        return


def register_terminal_routes(app: Flask, registry: TerminalSessionRegistry | None = None) -> None:
    sock = Sock(app)
    registry = registry or TerminalSessionRegistry()
    app.extensions["terminal_registry"] = registry
    # Don't let live shells outlive the server process.
    atexit.register(registry.kill_all)

    @app.get("/api/terminal/status")
    def terminal_status():
        reason = _env_reason()
        return jsonify({
            "enabled": reason is None,
            "running": registry.any_alive,
            "reason": reason,
            "shell": shell_name(),
        })

    @app.get("/api/terminal/sessions")
    def terminal_sessions():
        # _env_reason, not the full gate: same-origin GETs carry no Origin
        # header (same reasoning as /status).
        if _env_reason() is not None:
            return jsonify({"error": "forbidden"}), 403
        return jsonify({"sessions": registry.list(), "max": registry.MAX_SESSIONS})

    @app.post("/api/terminal/sessions")
    def terminal_session_create():
        if _gate_reason() is not None:
            return jsonify({"error": "forbidden"}), 403
        session = registry.create()
        if session is None:
            return jsonify({"error": "session limit reached"}), 409
        return jsonify({"id": session.id, "name": session.name}), 201

    @app.post("/api/terminal/sessions/<sid>/kill")
    def terminal_session_kill(sid):
        if _gate_reason() is not None:
            return jsonify({"error": "forbidden"}), 403
        if not registry.kill(sid):
            return jsonify({"error": "unknown session"}), 404
        return jsonify({"ok": True})

    @app.post("/api/terminal/kill")
    def terminal_kill():
        # Kills EVERY session — this backs Settings' "Restart terminal", which
        # is a full reset; the client reconciles its tabs via /sessions after.
        if _gate_reason() is not None:
            return jsonify({"error": "forbidden"}), 403
        registry.kill_all()
        return jsonify({"ok": True})

    @app.post("/api/terminal/resolve")
    def terminal_resolve():
        """Resolve candidate path tokens the client detected in a terminal line
        to absolute paths, reporting which exist. The client makes only the
        existing ones clickable, so path-shaped text never becomes a dead link.
        Gated exactly like the other terminal routes (same threat model: a
        single-user localhost app whose terminal already grants a full shell)."""
        if _gate_reason() is not None:
            return jsonify({"error": "forbidden"}), 403
        body = request.get_json(silent=True) or {}
        paths = body.get("paths")
        if not isinstance(paths, list):
            return jsonify({"error": "paths must be a list"}), 400
        sid = body.get("session")
        bases = resolve_bases(registry.pid_for(sid if isinstance(sid, str) else None))
        resolved = []
        for token in paths:
            if not isinstance(token, str) or not token:
                continue
            abs_path, exists = resolve_path(token, bases)
            resolved.append({"input": token, "abs": abs_path, "exists": exists})
        return jsonify({"resolved": resolved})

    @app.post("/api/terminal/open")
    def terminal_open():
        """Open an already-resolved absolute path in the user's editor at an
        optional line/col. Fail-soft: any error returns opened=false rather than
        raising, so a missing editor never surfaces as a 500."""
        if _gate_reason() is not None:
            return jsonify({"error": "forbidden"}), 403
        body = request.get_json(silent=True) or {}
        path = body.get("path")
        if not isinstance(path, str) or not path:
            return jsonify({"error": "path is required"}), 400
        # Confine the launch to the terminal's own working directories (shell
        # cwd, server cwd, home) and normalize the untrusted path to its real,
        # canonical form. Everything below uses this sanitized value, never the
        # raw client string. Outside the bases -> refuse.
        sid = body.get("session")
        safe = safe_editor_path(
            path, resolve_bases(registry.pid_for(sid if isinstance(sid, str) else None))
        )
        # Never launch on a non-file, even though the client only sends paths it
        # got back as exists=true — the state could have changed, and this is the
        # authoritative check before spawning a process.
        if safe is None or not os.path.isfile(safe):
            return jsonify({"opened": False, "editor": None})
        editor = detect_editor()
        if editor is None:
            return jsonify({"opened": False, "editor": None})
        line = _coerce_int(body.get("line"))
        col = _coerce_int(body.get("col"))
        try:
            argv = build_open_argv(editor, safe, line, col)
            if argv is None:  # Windows startfile sentinel
                os.startfile(safe)  # type: ignore[attr-defined]
            else:
                # Detached: the editor outlives this request; we don't wait on it.
                subprocess.Popen(argv, start_new_session=True)
            return jsonify({"opened": True, "editor": editor.name})
        except (OSError, ValueError):
            _logger.warning("failed to open %s in %s", safe, editor.name, exc_info=True)
            return jsonify({"opened": False, "editor": editor.name})

    @sock.route("/api/terminal/ws")
    def terminal_ws(ws):
        if _gate_reason() is not None:
            ws.close(_WS_CLOSE_REFUSED)
            return
        session, close_code = resolve_ws_session(registry, request.args.get("session"))
        if session is None:
            ws.close(close_code)
            return
        manager = session.manager
        # Only one WS client may drain a session's PTY at a time; a second
        # concurrent reader would race the first and produce garbled/doubled
        # output. Other sessions are unaffected.
        if not session.conn_lock.acquire(blocking=False):
            try:
                ws.send("0\r\n[terminal already open in another window]\r\n")
            finally:
                ws.close(_WS_CLOSE_BUSY)
            return
        try:
            if not setup_terminal_session(manager, ws):
                # Don't close here:
                # flask-sock sends the close frame after this handler returns,
                # i.e. after the outer finally has released _conn_lock, so a
                # client that reconnects the instant it sees the close finds
                # the lock free instead of a spurious "already open" refusal.
                return

            stop = threading.Event()
            reader = threading.Thread(
                target=pump_terminal_out, args=(manager, ws, stop), daemon=True
            )
            reader.start()
            try:
                terminal_read_loop(ws, manager, stop, _apply_control)
            finally:
                stop.set()
                # Join the reader BEFORE releasing the conn lock: a reader still
                # draining the shared PTY when the next client acquires the lock
                # would race the new reader (garbled/lost output). Both backends'
                # read() is time-bounded (Unix select timeout, Windows empty-read
                # sleep), so this returns promptly; bound it regardless.
                reader.join(timeout=2)
        finally:
            session.conn_lock.release()
