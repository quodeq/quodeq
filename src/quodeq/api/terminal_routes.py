"""WebSocket + control routes for the embedded terminal.

The WS handshake is a GET, which api/security.py's CSRF hook exempts, so this
module enforces the Origin check itself via terminal_gate_reason."""
from __future__ import annotations

import atexit
import json
import os
import struct
import threading

from flask import Flask, current_app, jsonify, request
from flask_sock import Sock

from quodeq.terminal.gate import terminal_gate_reason
from quodeq.terminal.manager import TerminalManager


def _gate_reason() -> str | None:
    return terminal_gate_reason(
        host=current_app.config.get("QUODEQ_BIND_HOST", ""),
        api_key=current_app.config.get("QUODEQ_API_KEY"),
        origin=request.headers.get("Origin"),
        request_host=request.host,
    )


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


def register_terminal_routes(app: Flask, manager: TerminalManager | None = None) -> None:
    sock = Sock(app)
    manager = manager or TerminalManager()
    app.extensions["terminal_manager"] = manager
    # Don't let a live shell outlive the server process.
    atexit.register(manager.kill)

    # Only one WS client may drain the single PTY at a time; a second concurrent
    # reader would race the first and produce garbled/doubled output.
    _conn_lock = threading.Lock()

    @app.get("/api/terminal/status")
    def terminal_status():
        reason = _gate_reason()
        return jsonify({"enabled": reason is None, "running": manager.alive, "reason": reason})

    @app.post("/api/terminal/kill")
    def terminal_kill():
        if _gate_reason() is not None:
            return jsonify({"error": "forbidden"}), 403
        manager.kill()
        return jsonify({"ok": True})

    @sock.route("/api/terminal/ws")
    def terminal_ws(ws):
        if _gate_reason() is not None:
            ws.close()
            return
        if not _conn_lock.acquire(blocking=False):
            try:
                ws.send("0\r\n[terminal already open in another window]\r\n")
            finally:
                ws.close()
            return
        try:
            try:
                manager.ensure_session(cwd=os.path.expanduser("~"), cols=80, rows=24)
                # Replay scrollback so a reattaching client sees recent history.
                sb = manager.scrollback()
                if sb:
                    ws.send("0" + sb.decode("utf-8", "replace"))
            except Exception:
                # Spawn failure or early disconnect must not propagate past
                # flask-sock (would surface as a 500); close cleanly instead.
                try:
                    ws.close()
                except Exception:
                    pass
                return

            stop = threading.Event()

            def _pump_out():
                while not stop.is_set():
                    data = manager.read(65536)
                    if not data:
                        if not manager.alive:
                            break
                        continue
                    try:
                        ws.send("0" + data.decode("utf-8", "replace"))
                    except Exception:
                        break
                stop.set()

            reader = threading.Thread(target=_pump_out, daemon=True)
            reader.start()
            try:
                while not stop.is_set():
                    msg = ws.receive(timeout=1)
                    if msg is None:
                        continue
                    tag, payload = msg[:1], msg[1:]
                    if tag == "0":
                        manager.write(payload.encode("utf-8"))
                    elif tag == "1":
                        _apply_control(manager, payload)
            except Exception:
                pass
            finally:
                stop.set()
        finally:
            _conn_lock.release()
