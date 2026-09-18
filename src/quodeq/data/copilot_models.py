"""Read account-available models through Copilot's SDK-compatible stdio RPC."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from quodeq.shared.copilot import build_copilot_env
from quodeq.shared.errors import ClientMessageError
from quodeq.shared.utils import sanitize_sensitive

_log = logging.getLogger(__name__)
_DISCOVERY_TIMEOUT_S = 15
_STOP_TIMEOUT_S = 2
_MAX_MESSAGE_BYTES = 1024 * 1024
_REQUEST_ID = "quodeq-models"


class _ModelDiscoveryError(ClientMessageError):
    """A safe explanation for a failed Copilot model lookup."""


def _rpc_error_message(error: object) -> str:
    message = error.get("message") if isinstance(error, dict) else None
    text = message.lower() if isinstance(message, str) else ""
    if any(word in text for word in ("authenticat", "login", "log in", "sign in")):
        return "Copilot authentication failed. Sign in to the dedicated Quodeq profile and retry."
    if any(word in text for word in ("policy", "forbidden", "not authorized", "access denied")):
        return "Your account or company policy does not allow this Copilot model lookup."
    return "Copilot rejected the model lookup. Check your connection and account access."


def _model_ids(result: object) -> list[str]:
    entries = result.get("models") if isinstance(result, dict) else None
    if not isinstance(entries, list):
        raise _ModelDiscoveryError("Copilot returned an invalid model list.")
    available = []
    for entry in entries:
        model_id = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(model_id, str) or not model_id.strip():
            raise _ModelDiscoveryError("Copilot returned an invalid model ID.")
        policy = entry.get("policy")
        if policy is not None:
            if not isinstance(policy, dict):
                raise _ModelDiscoveryError("Copilot returned an invalid model policy.")
            if policy.get("state") != "enabled":
                continue
        available.append(model_id)
    if not available:
        raise _ModelDiscoveryError("Copilot returned no available models for this account.")
    return list(dict.fromkeys(["auto", *available]))


async def _read_models(stdout: asyncio.StreamReader) -> list[str]:
    while True:
        header = await stdout.readuntil(b"\r\n\r\n")
        if not header.startswith(b"Content-Length:"):
            raise _ModelDiscoveryError("Copilot returned an invalid RPC header.")
        length = int(header.removeprefix(b"Content-Length:").strip())
        if not 0 < length <= _MAX_MESSAGE_BYTES:
            raise _ModelDiscoveryError("Copilot returned an invalid RPC message length.")
        response = json.loads(await stdout.readexactly(length))
        if not isinstance(response, dict):
            raise _ModelDiscoveryError("Copilot returned an invalid RPC response.")
        if response.get("id") != _REQUEST_ID:
            continue
        if "error" in response:
            raise _ModelDiscoveryError(_rpc_error_message(response["error"]))
        return _model_ids(response.get("result"))


async def _query_models(env: dict[str, str], timeout_s: float) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="quodeq-copilot-models-") as directory:
        process = None
        try:
            async with asyncio.timeout(timeout_s):
                process = await asyncio.create_subprocess_exec(
                    "copilot", "--headless", "--stdio", "--no-auto-update",
                    "--disable-builtin-mcps", "--no-custom-instructions", "--no-ask-user",
                    cwd=Path(directory), env=env, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                if process.stdin is None or process.stdout is None:
                    raise RuntimeError("Could not open Copilot model discovery pipes.")
                body = json.dumps({
                    "jsonrpc": "2.0", "id": _REQUEST_ID, "method": "models.list", "params": {},
                }).encode("utf-8")
                process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
                await process.stdin.drain()
                return await _read_models(process.stdout)
        finally:
            if process is not None:
                if process.returncode is None:
                    process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), _STOP_TIMEOUT_S)
                except TimeoutError:
                    process.kill()
                    await process.wait()


def fetch_copilot_models(
    *, env: dict[str, str] | None = None, timeout_s: float = _DISCOVERY_TIMEOUT_S,
) -> dict[str, object]:
    """Return models or a logged discovery error, without sending a model prompt."""
    try:
        isolated_env = build_copilot_env(dict(os.environ) if env is None else env)
        return {"models": asyncio.run(_query_models(isolated_env, timeout_s))}
    except TimeoutError:
        message = "Copilot model discovery timed out. Check your connection and retry."
        detail = message
    except _ModelDiscoveryError as exc:
        message = detail = exc.public_message
    except (OSError, ValueError, RuntimeError, EOFError, asyncio.LimitOverrunError) as exc:
        detail = sanitize_sensitive(str(exc))
        message = "Could not load Copilot models. Check your CLI installation, dedicated profile and connection."
    _log.warning("Copilot model discovery failed: %s", detail)
    return {"models": [], "error": message, "error_code": "COPILOT_MODELS_UNAVAILABLE"}
