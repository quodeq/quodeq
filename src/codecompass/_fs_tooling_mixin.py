from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from codecompass.adapters.fs.report_parser import safe_read_dir


class FsToolingMixin:
    """Mixin for browse_repo and AI client discovery methods."""

    def browse_repo(self, path: str | None):
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

    def get_ai_clients(self):
        candidates = [
            {"id": "claude", "label": "Claude"},
            {"id": "codex", "label": "Codex"},
            {"id": "copilot", "label": "Copilot"},
        ]
        return {"clients": [c for c in candidates if shutil.which(c["id"])]}

    def _get_cli_models(self, client_id: str):
        if not shutil.which(client_id):
            return {"models": []}
        try:
            result = subprocess.run(
                [client_id, "/models"],
                capture_output=True,
                text=True,
                timeout=8,
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

    def get_client_models(self, client_id: str):
        fetcher = self._model_fetchers.get(client_id, self._get_cli_models)
        return fetcher(client_id)

    def _get_claude_models(self, _client_id: str = "claude"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read())
                models = [m["id"] for m in data.get("data", []) if m.get("id")]
                if models:
                    return {"models": models}
            except Exception:
                pass
        return {"models": [
            "claude-opus-4-5",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
        ]}
