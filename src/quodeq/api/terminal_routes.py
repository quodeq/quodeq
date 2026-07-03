"""WebSocket + control routes for the embedded terminal.

The WS handshake is a GET, which api/security.py's CSRF hook exempts, so this
module enforces the Origin check itself via terminal_gate_reason."""
from __future__ import annotations

import json
import os
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


def _apply_control(manager, payload: str) -> None:
    """Apply a control frame's resize; ignore malformed input (never raise)."""
    try:
        ctrl = json.loads(payload)
        rs = ctrl.get("resize") if isinstance(ctrl, dict) else None
        if rs:
            manager.resize(int(rs["cols"]), int(rs["rows"]))
    except (ValueError, KeyError, TypeError):
        return


def register_terminal_routes(app: Flask, manager: TerminalManager | None = None) -> None:
    sock = Sock(app)
    manager = manager or TerminalManager()
    app.extensions["terminal_manager"] = manager

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
        manager.ensure_session(cwd=os.path.expanduser("~"), cols=80, rows=24)
        # Replay scrollback so a reattaching client sees recent history.
        sb = manager.scrollback()
        if sb:
            ws.send("0" + sb.decode("utf-8", "replace"))

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
