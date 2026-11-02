"""AI CLI model discovery adapter — the process boundary for CLI model listing.

Two sources: the plain ``<cli> /models`` probe, and the live catalogs Claude
Code and Codex hand back over their JSON-lines protocols.

``services/tooling_mixin.py`` owns the policy (client allowlist, isalnum
guard, output-token parsing); this module owns the process boundary: is the
binary installed, run it, and hand back raw stdout. Mirrors how
``data/fs/repo_clone.py`` wraps git behind ``ports.clone_repo``.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time


def run_cli_models_command(
    client_id: str, *, timeout_s: float, args: tuple[str, ...] = ("/models",),
) -> str:
    """Run ``<client_id> <args>`` (``/models`` by default; agy's is ``models``)
    and return its stdout, or "" on any failure.

    "" covers: the binary is not installed, it times out, it exits non-zero,
    or the process cannot be started at all.
    """
    if not shutil.which(client_id):
        return ""
    try:
        result = subprocess.run(
            [client_id, *args],
            capture_output=True,
            text=True, encoding="utf-8",
            timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return result.stdout if result.returncode == 0 else ""


# --- Live model catalogs -----------------------------------------------------
#
# Claude Code and Codex both describe the models the signed-in account can use
# over a JSON-lines protocol, without sending a prompt: Claude Code answers the
# stream-json ``initialize`` control request, Codex's app-server answers
# ``model/list``. Each catalog entry is a plain dict:
#   id, label, description, efforts (list), defaultEffort (str | None),
#   isDefault (bool), pinned (bool: a dated version rather than an alias).

_log = logging.getLogger(__name__)

_CLAUDE_ARGV = (
    "--print", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
)
_CLAUDE_INIT = {"type": "control_request", "request_id": "quodeq-models", "request": {"subtype": "initialize"}}
_CLAUDE_REPLY_TYPE = "control_response"
_CLAUDE_DEFAULT_ALIAS = "default"  # Claude Code's "use the recommended model" entry
_CLAUDE_PINNED_PREFIX = "claude-"  # dated ids; aliases (opus, sonnet) never carry it

_CODEX_ARGV = ("app-server",)
_CODEX_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"clientInfo": {"name": "quodeq", "version": "1"}}}
_CODEX_INITIALIZED = {"jsonrpc": "2.0", "method": "initialized"}
_CODEX_MAX_PAGES = 5
_CODEX_FIRST_LIST_ID = _CODEX_INIT["id"] + 1  # model/list pages count up from here

_OS_NAME_NT = "nt"
_STOP_TIMEOUT_S = 2


class CatalogUnavailable(Exception):
    """The CLI did not hand back a usable model list."""


class _JsonLinesSession:
    """A CLI spoken to in JSON lines: one request per line out, one reply per line in.

    A reader thread feeds a queue so every wait has a deadline on Windows
    too, where ``select`` does not work on pipes.
    """

    def __init__(self, argv: list[str], env: dict[str, str], deadline: float) -> None:
        self._deadline = deadline
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._process = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", env=env, cwd=tempfile.gettempdir(),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == _OS_NAME_NT else 0,
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def send(self, message: dict) -> None:
        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
        except OSError as exc:  # BrokenPipeError: the CLI exited early
            raise CatalogUnavailable("the CLI closed its input") from exc

    def wait_for(self, matches) -> dict:
        """The first message *matches* accepts; lines that are not JSON are skipped."""
        while True:
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise CatalogUnavailable("timed out")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise CatalogUnavailable("timed out") from exc
            if line is None:
                raise CatalogUnavailable("the CLI exited before answering")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # banners and log lines share stdout on some versions
            if isinstance(message, dict) and matches(message):
                return message

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.kill()
        for pipe in (self._process.stdin, self._process.stdout):
            try:
                pipe.close()
            except OSError:
                _log.debug("Model-list CLI pipe already closed")
        try:
            self._process.wait(timeout=_STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            # The catalog is already read; a CLI slow to die is left to the OS.
            _log.debug("Model-list CLI did not exit within %ss", _STOP_TIMEOUT_S)


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _claude_catalog(session: _JsonLinesSession) -> list[dict]:
    session.send(_CLAUDE_INIT)
    reply = session.wait_for(lambda m: m.get("type") == _CLAUDE_REPLY_TYPE)
    body = _as_dict(reply.get("response"))
    models = _as_dict(body.get("response", body)).get("models")
    if not isinstance(models, list):
        raise CatalogUnavailable("no model list in the initialize reply")
    entries = [m for m in models if isinstance(m, dict) and isinstance(m.get("value"), str)]
    recommended = next(
        (m.get("resolvedModel") for m in entries if m["value"] == _CLAUDE_DEFAULT_ALIAS), None,
    )
    return [
        {
            "id": m["value"],
            "label": str(m.get("displayName") or m["value"]),
            "description": str(m.get("description") or ""),
            "efforts": [e for e in m.get("supportedEffortLevels") or [] if isinstance(e, str)],
            "defaultEffort": None,
            "isDefault": recommended is not None and m.get("resolvedModel") == recommended
            and not m["value"].startswith(_CLAUDE_PINNED_PREFIX),
            "pinned": m["value"].startswith(_CLAUDE_PINNED_PREFIX),
        }
        for m in entries if m["value"] != _CLAUDE_DEFAULT_ALIAS
    ]


def _codex_entry(m: dict) -> dict:
    efforts = [e.get("reasoningEffort") for e in m.get("supportedReasoningEfforts") or [] if isinstance(e, dict)]
    return {
        "id": m["id"],
        "label": str(m.get("displayName") or m["id"]),
        "description": str(m.get("description") or ""),
        "efforts": [e for e in efforts if isinstance(e, str)],
        "defaultEffort": m.get("defaultReasoningEffort") if isinstance(m.get("defaultReasoningEffort"), str) else None,
        "isDefault": bool(m.get("isDefault")),
        "pinned": False,
    }


def _codex_catalog(session: _JsonLinesSession) -> list[dict]:
    session.send(_CODEX_INIT)
    session.wait_for(lambda m: m.get("id") == _CODEX_INIT["id"])
    session.send(_CODEX_INITIALIZED)
    entries: list[dict] = []
    cursor = None
    for page in range(_CODEX_MAX_PAGES):
        request_id = _CODEX_FIRST_LIST_ID + page
        params = {"cursor": cursor} if cursor else {}
        session.send({"jsonrpc": "2.0", "id": request_id, "method": "model/list", "params": params})
        reply = session.wait_for(lambda m, rid=request_id: m.get("id") == rid)
        if "error" in reply:
            raise CatalogUnavailable("model/list was rejected")
        result = _as_dict(reply.get("result"))
        data = result.get("data")
        if not isinstance(data, list):
            raise CatalogUnavailable("no model list in the model/list reply")
        entries.extend(
            _codex_entry(m) for m in data
            if isinstance(m, dict) and isinstance(m.get("id"), str) and not m.get("hidden")
        )
        cursor = result.get("nextCursor")
        if not cursor:
            break
    return entries


_CATALOG_READERS = {"claude": (_CLAUDE_ARGV, _claude_catalog), "codex": (_CODEX_ARGV, _codex_catalog)}


def supports_model_catalog(client_id: str) -> bool:
    """Whether *client_id* can describe its models over a JSON-lines protocol."""
    return client_id in _CATALOG_READERS


def fetch_cli_model_catalog(client_id: str, *, env: dict[str, str], timeout_s: float) -> list[dict]:
    """The models *client_id*'s signed-in account offers, read without a prompt.

    Raises :class:`CatalogUnavailable` when the CLI is missing, slow, or
    answers with something that is not a model list.
    """
    argv_tail, read = _CATALOG_READERS[client_id]
    executable = shutil.which(client_id)
    if not executable:
        raise CatalogUnavailable("the CLI is not installed")
    try:
        session = _JsonLinesSession([executable, *argv_tail], env, time.monotonic() + timeout_s)
    except OSError as exc:
        raise CatalogUnavailable("the CLI could not be started") from exc
    try:
        entries = read(session)
    finally:
        session.close()
    if not entries:
        raise CatalogUnavailable("the CLI listed no models")
    return entries
