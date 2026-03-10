"""Shared utilities, constants, and helpers for the Quodeq package."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

_DEFAULTS_PATH = Path(__file__).resolve().parent / "defaults.json"


@dataclass
class Config:
    """Centralized configuration holder loaded from defaults.json.

    Replaces raw module-level mutable dict with a testable object that
    supports safe overrides via the :meth:`override` context manager.
    """

    _data: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def update(self, **overrides: Any) -> None:
        self._data.update(overrides)

    @contextmanager
    def override(self, **overrides: Any) -> Iterator[None]:
        """Temporarily override config values; restores originals on exit."""
        saved = {k: self._data[k] for k in overrides if k in self._data}
        removed = {k for k in overrides if k not in self._data}
        self._data.update(overrides)
        try:
            yield
        finally:
            self._data.update(saved)
            for k in removed:
                self._data.pop(k, None)

    @classmethod
    def from_file(cls, path: Path) -> Config:
        return cls(_data=json.loads(path.read_text()))


# Load network/service defaults from external config file (CWE-1051).
_config = Config.from_file(_DEFAULTS_PATH)

# Derived constants (not URLs, safe to keep inline).
ACTION_API_MODULE = "quodeq.action_api"

# Public accessors for defaults used as constants by other modules.
ANTHROPIC_API_URL: str = _config["anthropic_api_url"]
ANTHROPIC_API_VERSION: str = _config["anthropic_api_version"]
DEFAULT_HOST: str = _config["default_host"]


def configure(**overrides: Any) -> None:
    """Inject configuration overrides (useful for testing and deployment).

    Call before any ``get_*`` function to replace defaults loaded from
    ``defaults.json``.  Example::

        configure(ai_cmd_default="my-cli", action_api_port=9000)
    """
    _config.update(**overrides)


def is_repo_url(repo_input: str) -> bool:
    """Return True if the input looks like a remote repository URL."""
    return repo_input.startswith(("http://", "https://", "git@"))


def project_name_from_repo(repo: str) -> str:
    """Extract a human-readable project name from a repo path or URL."""
    if is_repo_url(repo):
        return repo.split("/")[-1].replace(".git", "")
    return Path(repo).name


def read_json(path: Path) -> dict:
    """Read and parse a JSON file, returning the parsed dict."""
    return json.loads(path.read_text())


def get_ai_provider() -> str:
    """Return the AI provider from environment or default."""
    return os.environ.get("AI_PROVIDER", _config["ai_provider_default"])


def get_ai_cmd() -> str:
    """Return the AI CLI command from environment or default."""
    return os.environ.get("AI_CMD", _config["ai_cmd_default"])


def get_ai_model() -> str | None:
    """Return the AI model from environment, or None."""
    return os.environ.get("AI_MODEL") or None


def get_action_api_port() -> int:
    """Return the action API port from environment or default."""
    raw = os.environ.get("QUODEQ_ACTION_API_PORT")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            import logging
            logging.getLogger(__name__).warning(
                "Invalid QUODEQ_ACTION_API_PORT=%r, using default", raw,
            )
    return _config["action_api_port"]


def get_action_api_host() -> str:
    """Return the action API host from environment or default."""
    return os.environ.get("QUODEQ_ACTION_API_HOST", _config["default_host"])


def get_dashboard_port() -> int:
    """Return the dashboard preview port from environment or default."""
    raw = os.environ.get("QUODEQ_DASHBOARD_PORT")
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            import logging
            logging.getLogger(__name__).warning(
                "Invalid QUODEQ_DASHBOARD_PORT=%r, using default", raw,
            )
    return _config["dashboard_port"]


def get_static_dist() -> str | None:
    """Return the static dist path from environment, or None."""
    return os.environ.get("QUODEQ_STATIC_DIST")


def get_evaluations_dir(default: str = "evaluations") -> str:
    """Return the evaluations directory from environment or default."""
    return os.environ.get("QUODEQ_EVALUATIONS_DIR", default)


def get_anthropic_api_key() -> str | None:
    """Return the Anthropic API key from environment, or None."""
    return os.environ.get("ANTHROPIC_API_KEY") or None


def get_asvs_url() -> str:
    """Return the OWASP ASVS JSON URL from environment or default."""
    return os.environ.get("QUODEQ_ASVS_URL", _config["asvs_url"])


def get_github_search_url() -> str:
    """Return the GitHub repository search URL from environment or default."""
    return os.environ.get("QUODEQ_GITHUB_SEARCH_URL", _config["github_search_url"])


def get_findings_file() -> str | None:
    """Return the findings file path from environment, or None."""
    return os.environ.get("FINDINGS_FILE")


def show_diff(path: Path, new_content: str) -> None:
    """Print a unified diff between *path*'s current content and *new_content*."""
    import difflib
    old_lines = path.read_text().splitlines(keepends=True) if path.exists() else []
    new_lines = new_content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=str(path), tofile="<new>"))
    if diff:
        print("".join(diff))
    else:
        print(f"[no changes] {path}")
