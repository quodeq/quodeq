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

from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.data.fs.report_parser import safe_read_dir
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


_DEFAULT_CLIENT_IDS = frozenset({"claude", "codex", "gemini"})


def get_allowed_client_ids(env: dict[str, str] | None = None) -> frozenset[str]:
    """Return the set of allowed AI client IDs (lazy, reads env on each call).

    Includes both hardcoded CLI tools and API providers from the provider
    config.  *env* overrides ``os.environ`` when provided, making the
    function testable without environment mutation.
    """
    environ = env if env is not None else os.environ
    if "QUODEQ_AI_CLIENTS" in environ:
        return frozenset(environ["QUODEQ_AI_CLIENTS"].split(","))
    # Include API providers from config alongside default CLI tools
    api_ids = frozenset(
        pid for pid, cfg in get_provider_configs().items()
        if cfg.get("type") == "api"
    )
    return _DEFAULT_CLIENT_IDS | api_ids


class FsToolingMixin:
    """Mixin for browse_repo and AI client discovery methods."""

    def __init__(self) -> None:
        self._model_fetchers: dict[str, Callable] = {}

    @staticmethod
    def _validate_browse_path(path: str | None) -> tuple[Path, dict[str, Any] | None]:
        """Resolve and validate a browse path. Returns (target, error_or_None)."""
        target = Path(path) if path else Path.home()
        target = target.resolve()
        if not target.is_relative_to(Path.home()):
            return target, {"error": "Path outside allowed boundary", "error_code": "PATH_OUTSIDE_BOUNDARY"}
        if not target.exists():
            return target, {"error": "Path not found", "error_code": "PATH_NOT_FOUND", "path": str(target)}
        if not target.is_dir():
            return target, {"error": "Path is not a directory", "error_code": "PATH_NOT_DIRECTORY", "path": str(target)}
        return target, None

    @staticmethod
    def _list_directories(target: Path) -> list[dict[str, Any]]:
        """List readable non-hidden subdirectories of *target*."""
        directories = []
        for entry in safe_read_dir(target):
            if entry.name.startswith(".") or not entry.is_dir():
                continue
            entry_path = target / entry.name
            if not os.access(entry_path, os.R_OK):
                continue
            directories.append({
                "name": entry.name,
                "path": str(entry_path),
                "isGitRepo": (entry_path / ".git").exists(),
            })
        directories.sort(key=lambda item: item["name"])
        return directories

    @staticmethod
    def _list_files(target: Path) -> list[dict[str, Any]]:
        """List readable non-hidden source files in *target*."""
        files: list[dict[str, Any]] = []
        for entry in safe_read_dir(target):
            if entry.name.startswith(".") or not entry.is_file():
                continue
            entry_path = target / entry.name
            if not os.access(entry_path, os.R_OK):
                continue
            files.append({
                "name": entry.name,
                "path": str(entry_path),
            })
        files.sort(key=lambda item: item["name"])
        return files

    @staticmethod
    def _build_browse_response(target: Path, directories: list[dict[str, Any]], files: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Assemble a browse_repo response from a validated target and directory list."""
        truncated = len(directories) > _BROWSE_DIR_LIMIT
        if truncated:
            directories = directories[:_BROWSE_DIR_LIMIT]
        parent = target.parent if target.parent != target else None
        response: dict[str, Any] = {
            "current": str(target),
            "parent": str(parent) if parent else None,
            "directories": directories,
            "isGitRepo": (target / ".git").exists(),
            "truncated": truncated,
        }
        if files is not None:
            response["files"] = files
        return response

    def browse_repo(self, path: str | None, include_files: bool = False) -> dict[str, Any]:
        """List directories (and optionally files) at the given path."""
        target, error = self._validate_browse_path(path)
        if error is not None:
            return error
        files = self._list_files(target) if include_files else None
        return self._build_browse_response(target, self._list_directories(target), files)

    # Default AI CLI candidates. Override via the QUODEQ_AI_CLIENTS env var
    # (comma-separated list of client IDs, e.g. "claude,codex").
    _CLI_CANDIDATES = [
        {"id": "claude", "label": "Claude"},
        {"id": "codex", "label": "Codex"},
        {"id": "gemini", "label": "Gemini"},
    ]

    def get_ai_clients(self, env: dict[str, str] | None = None) -> dict[str, list[dict[str, str]]]:
        """Return available AI clients (CLI tools that are installed + API providers).

        *env* overrides ``os.environ`` when provided, making the method
        testable without environment mutation.
        """
        environ = env if env is not None else os.environ
        clients: list[dict[str, str]] = []

        # CLI tools: only include if installed
        if "QUODEQ_AI_CLIENTS" in environ:
            ids = [c.strip() for c in environ["QUODEQ_AI_CLIENTS"].split(",") if c.strip()]
            candidates = [{"id": c, "label": c.capitalize()} for c in ids]
        else:
            candidates = self._CLI_CANDIDATES

        for c in candidates:
            if shutil.which(c["id"]):
                clients.append({**c, "type": "cli"})

        # API providers: always available (no CLI binary needed)
        provider_configs = get_provider_configs()
        for provider_id, cfg in provider_configs.items():
            if cfg.get("type") == "api" and provider_id != "custom":
                if not any(c["id"] == provider_id for c in clients):
                    clients.append({
                        "id": provider_id,
                        "label": provider_id.capitalize(),
                        "type": "api",
                    })

        # Sort by 'order' field from ai_providers.json
        clients.sort(key=lambda c: provider_configs.get(c["id"], {}).get("order", 50))

        return {"clients": clients}

    def _get_cli_models(self, client_id: str, env: dict[str, str] | None = None) -> dict[str, list[str]]:
        if client_id not in get_allowed_client_ids(env=env):
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

    def _get_claude_models(
        self, _client_id: str = "claude", api_key: str | None = None,
        key_fn: Callable[[], str | None] | None = None,
    ) -> dict[str, list[str]]:
        """Fetch Claude model list from the Anthropic API, with fallback.

        Pass *api_key* to supply a concrete key directly, or *key_fn* to
        override the global ``get_anthropic_api_key()`` accessor (e.g. for
        testing or per-request credential injection).
        """
        key = api_key or (key_fn or get_anthropic_api_key)()
        if key:
            models = _fetch_anthropic_models(key)
            if models:
                return {"models": models}
        return {"models": _load_fallback_claude_models()}
