"""Mixin providing repo browsing and AI client discovery for the filesystem provider."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from typing import Any

from quodeq.adapters.fs.report_parser import safe_read_dir
from quodeq.utils import ANTHROPIC_API_URL, ANTHROPIC_API_VERSION

_CLI_MODEL_TIMEOUT_S = 8
_ANTHROPIC_API_TIMEOUT_S = 8
_FALLBACK_CLAUDE_MODELS = [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
]


def _fetch_anthropic_models(api_key: str) -> list[str] | None:
    """Fetch model list from the Anthropic API. Returns None on failure."""
    try:
        req = urllib.request.Request(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
            },
        )
        with urllib.request.urlopen(req, timeout=_ANTHROPIC_API_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
        models = [m["id"] for m in data.get("data", []) if m.get("id")]
        return models if models else None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


class FsToolingMixin:
    """Mixin for browse_repo and AI client discovery methods."""

    def browse_repo(self, path: str | None) -> dict[str, Any]:
        """List directories at the given path for repository browsing."""
        target = Path(path) if path else Path.home()
        target = target.resolve()
        if not target.exists():
            return {"error": "Path not found", "path": str(target)}
        if not target.is_dir():
            return {"error": "Path is not a directory", "path": str(target)}

        directories = []
        for entry in safe_read_dir(target):
            if entry.name.startswith("."):
                continue
            if not entry.is_dir():
                continue
            entry_path = target / entry.name
            try:
                os.access(entry_path, os.R_OK)
            except OSError:
                continue
            directories.append(
                {
                    "name": entry.name,
                    "path": str(entry_path),
                    "isGitRepo": (entry_path / ".git").exists(),
                }
            )

        directories.sort(key=lambda item: item["name"])
        parent = target.parent if target.parent != target else None
        return {
            "current": str(target),
            "parent": str(parent) if parent else None,
            "directories": directories,
            "isGitRepo": (target / ".git").exists(),
        }

    def get_ai_clients(self) -> dict[str, list[dict[str, str]]]:
        """Return AI CLI clients that are installed on the system."""
        candidates = [
            {"id": "claude", "label": "Claude"},
            {"id": "codex", "label": "Codex"},
            {"id": "copilot", "label": "Copilot"},
        ]
        return {"clients": [c for c in candidates if shutil.which(c["id"])]}

    def _get_cli_models(self, client_id: str) -> dict[str, list[str]]:
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
            if token and token[0] not in ("#", "=", "-", "[", "("):
                models.append(token)
        return {"models": models}

    def get_client_models(self, client_id: str) -> dict[str, list[str]]:
        """Return available models for a specific AI client."""
        fetcher = self._model_fetchers.get(client_id, self._get_cli_models)
        return fetcher(client_id)

    def _get_claude_models(self, _client_id: str = "claude", api_key: str | None = None) -> dict[str, list[str]]:
        # API key is intentionally read from env at call time (not cached) for security.
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if key:
            models = _fetch_anthropic_models(key)
            if models:
                return {"models": models}
        return {"models": list(_FALLBACK_CLAUDE_MODELS)}
