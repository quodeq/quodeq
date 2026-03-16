"""Mixin providing repo browsing and AI client discovery for the filesystem provider."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from typing import Any, Callable

from quodeq.adapters.fs.report_parser import safe_read_dir
from quodeq.shared.config_loader import get_anthropic_api_url, get_anthropic_api_version
from quodeq.shared.utils import get_anthropic_api_key, read_json

_CLI_MODEL_TIMEOUT_S = 8
_CLI_OUTPUT_IGNORE_PREFIXES = {"#", "=", "-", "[", "("}
_ANTHROPIC_API_TIMEOUT_S = 8
_BROWSE_DIR_LIMIT = 500
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_AI_DEFAULTS_PATH = _PACKAGE_ROOT / "config" / "ai_defaults.json"


def _load_fallback_claude_models() -> list[str]:
    """Load fallback Claude model list from config/ai_defaults.json."""
    try:
        data = read_json(_AI_DEFAULTS_PATH)
        return data.get("fallback_claude_models", [])
    except (OSError, json.JSONDecodeError):
        return []


def _fetch_anthropic_models(api_key: str) -> list[str] | None:
    """Fetch model list from the Anthropic API. Returns None on failure."""
    try:
        req = urllib.request.Request(
            get_anthropic_api_url(),
            headers={
                "x-api-key": api_key,
                "anthropic-version": get_anthropic_api_version(),
            },
        )
        with urllib.request.urlopen(req, timeout=_ANTHROPIC_API_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        return models if models else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


_DEFAULT_CLIENT_IDS = frozenset({"claude", "codex", "copilot"})


def get_allowed_client_ids(env: dict[str, str] | None = None) -> frozenset[str]:
    """Return the set of allowed AI client IDs (lazy, reads env on each call).

    *env* overrides ``os.environ`` when provided, making the function
    testable without environment mutation.
    """
    environ = env if env is not None else os.environ
    if "QUODEQ_AI_CLIENTS" in environ:
        return frozenset(environ["QUODEQ_AI_CLIENTS"].split(","))
    return _DEFAULT_CLIENT_IDS


class FsToolingMixin:
    """Mixin for browse_repo and AI client discovery methods."""

    def __init__(self) -> None:
        self._model_fetchers: dict[str, Callable] = {}

    def browse_repo(self, path: str | None) -> dict[str, Any]:
        """List directories at the given path for repository browsing."""
        target = Path(path) if path else Path.home()
        target = target.resolve()
        if not target.is_relative_to(Path.home()):
            return {"error": "Path outside allowed boundary", "error_code": "PATH_OUTSIDE_BOUNDARY"}
        if not target.exists():
            return {"error": "Path not found", "error_code": "PATH_NOT_FOUND", "path": str(target)}
        if not target.is_dir():
            return {"error": "Path is not a directory", "error_code": "PATH_NOT_DIRECTORY", "path": str(target)}

        directories = []
        for entry in safe_read_dir(target):
            if entry.name.startswith("."):
                continue
            if not entry.is_dir():
                continue
            entry_path = target / entry.name
            if not os.access(entry_path, os.R_OK):
                continue
            directories.append(
                {
                    "name": entry.name,
                    "path": str(entry_path),
                    "isGitRepo": (entry_path / ".git").exists(),
                }
            )

        directories.sort(key=lambda item: item["name"])
        truncated = len(directories) > _BROWSE_DIR_LIMIT
        if truncated:
            directories = directories[:_BROWSE_DIR_LIMIT]
        parent = target.parent if target.parent != target else None
        return {
            "current": str(target),
            "parent": str(parent) if parent else None,
            "directories": directories,
            "isGitRepo": (target / ".git").exists(),
            "truncated": truncated,
        }

    _CLI_CANDIDATES = [
        {"id": "claude", "label": "Claude"},
        {"id": "codex", "label": "Codex"},
        {"id": "copilot", "label": "Copilot"},
    ]

    def get_ai_clients(self, env: dict[str, str] | None = None) -> dict[str, list[dict[str, str]]]:
        """Return AI CLI clients that are installed on the system.

        *env* overrides ``os.environ`` when provided, making the method
        testable without environment mutation.
        """
        environ = env if env is not None else os.environ
        if "QUODEQ_AI_CLIENTS" in environ:
            ids = [c.strip() for c in environ["QUODEQ_AI_CLIENTS"].split(",") if c.strip()]
            candidates = [{"id": c, "label": c.capitalize()} for c in ids]
        else:
            candidates = self._CLI_CANDIDATES
        return {"clients": [c for c in candidates if shutil.which(c["id"])]}

    def _get_cli_models(self, client_id: str) -> dict[str, list[str]]:
        if client_id not in get_allowed_client_ids():
            return {"models": []}
        if not shutil.which(client_id):
            return {"models": []}
        try:
            result = subprocess.run(
                [client_id, "/models"],
                capture_output=True,
                text=True,
                timeout=_CLI_MODEL_TIMEOUT_S,
            )
            output = result.stdout if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, OSError):
            return {"models": []}
        models = []
        for line in output.splitlines():
            token = line.strip().split()[0] if line.strip() else ""
            if token and token[0] not in _CLI_OUTPUT_IGNORE_PREFIXES:
                models.append(token)
        return {"models": models}

    def get_client_models(self, client_id: str) -> dict[str, list[str]]:
        """Return available models for a specific AI client."""
        fetcher = self._model_fetchers.get(client_id, self._get_cli_models)
        return fetcher(client_id)

    def _get_claude_models(self, _client_id: str = "claude", api_key: str | None = None) -> dict[str, list[str]]:
        key = api_key or get_anthropic_api_key()
        if key:
            models = _fetch_anthropic_models(key)
            if models:
                return {"models": models}
        return {"models": _load_fallback_claude_models()}
