"""Read account-available models through Copilot's SDK-compatible stdio RPC."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.copilot import build_copilot_env
from quodeq.shared.errors import ClientMessageError
from quodeq.shared.utils import sanitize_sensitive

_log = logging.getLogger(__name__)
_DISCOVERY_TIMEOUT_S = 15
_STOP_TIMEOUT_S = 2
_MAX_MESSAGE_BYTES = 1024 * 1024
_REQUEST_ID = "quodeq-models"

# LSP-style RPC framing: the writer builds the header from these, the reader
# checks/strips the same prefix and terminator, so both sides stay in sync.
_RPC_HEADER_NAME = "Content-Length"
_RPC_HEADER_PREFIX = f"{_RPC_HEADER_NAME}:".encode()
_RPC_TERMINATOR = b"\r\n\r\n"
# JSON-RPC error field: unrelated to any closed vocabulary (ExitReason/
# FileDoneStatus also spell "error") -- named so the vocab-literal ratchet
# doesn't mistake this RPC-protocol key for one of those.
_RPC_ERROR_KEY = "error"


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
        header = await stdout.readuntil(_RPC_TERMINATOR)
        if not header.startswith(_RPC_HEADER_PREFIX):
            raise _ModelDiscoveryError("Copilot returned an invalid RPC header.")
        length = int(header.removeprefix(_RPC_HEADER_PREFIX).strip())
        if not 0 < length <= _MAX_MESSAGE_BYTES:
            raise _ModelDiscoveryError("Copilot returned an invalid RPC message length.")
        response = json.loads(await stdout.readexactly(length))
        if not isinstance(response, dict):
            raise _ModelDiscoveryError("Copilot returned an invalid RPC response.")
        if response.get("id") != _REQUEST_ID:
            continue
        if _RPC_ERROR_KEY in response:
            raise _ModelDiscoveryError(_rpc_error_message(response[_RPC_ERROR_KEY]))
        return _model_ids(response.get("result"))


_CLEANUP_RETRIES = 5
_CLEANUP_RETRY_DELAY_S = 0.1

# Injectable in place of asyncio.create_subprocess_exec so tests can supply a
# fake spawner instead of monkeypatching the asyncio module globally.
ProcessFactory = Callable[..., Awaitable[asyncio.subprocess.Process]]


async def _remove_scratch_dir(directory: str) -> None:
    """Best-effort removal of the discovery scratch dir. Never raises.

    On Windows the just-terminated CLI (or a child of it) can hold a handle
    on its cwd for a moment after ``wait()`` returns, so the first rmtree can
    fail with WinError 32. Raising here used to discard an already-successful
    model list (the exception fired in TemporaryDirectory.__exit__, after the
    return value existed) and report COPILOT_MODELS_UNAVAILABLE for a run
    that worked. Retry briefly; if the handle outlives the retries, leave the
    directory to the OS temp cleaner rather than fail the discovery.
    """
    for attempt in range(_CLEANUP_RETRIES):
        try:
            shutil.rmtree(directory)
            return
        except OSError as exc:
            if attempt == _CLEANUP_RETRIES - 1:
                _log.debug(
                    "Leaving Copilot scratch dir %s to the OS temp cleaner: %s",
                    directory, exc,
                )
                return
            await asyncio.sleep(_CLEANUP_RETRY_DELAY_S)


async def _query_models(
    env: dict[str, str], timeout_s: float, *, process_factory: ProcessFactory | None = None,
) -> list[str]:
    # Not TemporaryDirectory: its __exit__ raises on the Windows handle race
    # documented on _remove_scratch_dir, and that must not outrank the result.
    spawn = process_factory or asyncio.create_subprocess_exec
    directory = tempfile.mkdtemp(prefix="quodeq-copilot-models-")
    process = None
    try:
        async with asyncio.timeout(timeout_s):
            process = await spawn(
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
            process.stdin.write(f"{_RPC_HEADER_NAME}: {len(body)}".encode() + _RPC_TERMINATOR + body)
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
        await _remove_scratch_dir(directory)


def fetch_copilot_models(
    *,
    env: dict[str, str] | None = None,
    timeout_s: float = _DISCOVERY_TIMEOUT_S,
    process_factory: ProcessFactory | None = None,
) -> dict[str, object]:
    """Return models or a logged discovery error, without sending a model prompt.

    *process_factory* stands in for ``asyncio.create_subprocess_exec`` (same
    signature); tests can inject a fake spawner instead of monkeypatching the
    asyncio module.
    """
    try:
        isolated_env = build_copilot_env(dict(resolve_env(env)))
        return {
            "models": asyncio.run(
                _query_models(isolated_env, timeout_s, process_factory=process_factory),
            ),
        }
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
