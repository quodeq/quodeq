"""Minimal JSON-RPC 2.0 over stdio (stream-parameterized copy; no analysis import)."""
from __future__ import annotations

import json
from typing import TextIO

_VERSION = "2.0"


def send(msg: dict, out: TextIO) -> None:
    out.write(json.dumps(msg) + "\n")
    out.flush()


def ok(req_id: object, result: dict) -> dict:
    return {"jsonrpc": _VERSION, "id": req_id, "result": result}


def err(req_id: object, code: int, message: str) -> dict:
    return {"jsonrpc": _VERSION, "id": req_id, "error": {"code": code, "message": message}}


def read_message(stream: TextIO) -> dict | None:
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None
