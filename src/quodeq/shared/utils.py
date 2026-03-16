"""Shared utilities, constants, and helpers for the Quodeq package."""
from __future__ import annotations

import json
import logging
import os
import re as _re
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

_DEFAULTS_PATH = Path(__file__).resolve().parent / "defaults.json"
_DEFAULT_EVALUATIONS_DIR = Path.home() / ".quodeq" / "evaluations"

TEXT_ENCODING = "utf-8"
"""Standard text encoding used across the codebase for file I/O."""


# ── Centralized I/O helpers ─────────────────────────────────────────────
# Every file read/write should go through these so encoding is handled once.


def read_text(path: Path, *, errors: str = "strict") -> str:
    """Read a text file with the standard encoding."""
    return path.read_text(encoding=TEXT_ENCODING, errors=errors)


def write_text(path: Path, content: str) -> None:
    """Write a text file with the standard encoding."""
    path.write_text(content, encoding=TEXT_ENCODING)


def read_json(path: Path) -> Any:
    """Read and parse a JSON file with the standard encoding."""
    return json.loads(path.read_text(encoding=TEXT_ENCODING))


def open_text(path: str | Path, mode: str = "r") -> Any:
    """Open a text file with the standard encoding. Use as a context manager."""
    return open(path, mode, encoding=TEXT_ENCODING)


SENSITIVE_PATTERNS = _re.compile(
    r"(api[_-]?key|token|secret|password|authorization)[=:\s]+\S+",
    _re.IGNORECASE,
)
"""Compiled regex for detecting secrets in log/error output."""


def sanitize_sensitive(text: str) -> str:
    """Mask potential secrets in *text* for safe logging/display."""
    return SENSITIVE_PATTERNS.sub(r"\1=***", text)


@dataclass
class Config:
    """Centralized configuration holder loaded from defaults.json.

    Replaces raw module-level mutable dict with a testable object that
    supports safe overrides via the :meth:`override` context manager.
    """

    _data: dict[str, Any] = field(default_factory=dict, init=False)

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
        obj = cls()
        obj._data = read_json(path)
        return obj


# Derived constants (not URLs, safe to keep inline).
ACTION_API_MODULE = "quodeq.action_api"


_config_lock = threading.Lock()
_config_instance: Config | None = None


def _get_config() -> Config:
    """Return the lazily-loaded singleton Config instance (thread-safe)."""
    global _config_instance
    if _config_instance is None:
        with _config_lock:
            if _config_instance is None:
                _config_instance = Config.from_file(_DEFAULTS_PATH)
    return _config_instance


IS_WIN32: bool = sys.platform == "win32"
"""True when the current platform is Windows (win32)."""


def __getattr__(name: str) -> str:
    """Lazy accessor for config-derived constants (ANTHROPIC_API_URL, etc.)."""
    from quodeq.shared.config_loader import __getattr__ as _cl_getattr
    return _cl_getattr(name)


def is_repo_url(repo_input: str) -> bool:
    """Return True if the input looks like a remote repository URL."""
    return repo_input.startswith(("http://", "https://", "git@"))


def project_name_from_repo(repo: str) -> str:
    """Extract a human-readable project name from a repo path or URL."""
    if is_repo_url(repo):
        return repo.split("/")[-1].replace(".git", "")
    return Path(repo).name


def read_json(path: Path) -> dict[str, Any]:
    """Read and parse a JSON file, returning the parsed dict."""
    try:
        return json.loads(path.read_text(encoding=TEXT_ENCODING))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON file {path}: {exc}") from exc


def get_ai_provider() -> str:
    """Return the AI provider from environment or default."""
    return os.environ.get("AI_PROVIDER", _get_config()["ai_provider_default"])


def get_ai_cmd() -> str:
    """Return the AI CLI command from environment or default."""
    return os.environ.get("AI_CMD", _get_config()["ai_cmd_default"])


def get_ai_model() -> str | None:
    """Return the AI model from environment, or None."""
    return os.environ.get("AI_MODEL") or None


def _env_int(var: str, default: int) -> int:
    """Read an environment variable as an int, warn and return *default* on failure."""
    raw = os.environ.get(var)
    if raw is not None:
        try:
            return int(raw)
        except ValueError:
            logging.getLogger(__name__).warning(
                "Invalid %s=%r, using default", var, raw,
            )
    return default


def get_action_api_port() -> int:
    """Return the action API port from environment or default."""
    return _env_int("QUODEQ_ACTION_API_PORT", _get_config()["action_api_port"])


def get_action_api_host() -> str:
    """Return the action API host from environment or default."""
    return os.environ.get("QUODEQ_ACTION_API_HOST", _get_config()["default_host"])


def get_dashboard_port() -> int:
    """Return the dashboard preview port from environment or default."""
    return _env_int("QUODEQ_DASHBOARD_PORT", _get_config()["dashboard_port"])


def get_static_dist() -> str | None:
    """Return the static dist path from environment, or the bundled static dir."""
    from_env = os.environ.get("QUODEQ_STATIC_DIST")
    if from_env:
        return from_env
    # Fall back to static assets bundled inside the package
    bundled = Path(__file__).resolve().parent.parent / "static"
    if bundled.is_dir() and (bundled / "index.html").exists():
        return str(bundled)
    return None


def get_evaluations_dir(default: str | None = None) -> str:
    """Return the evaluations directory from environment or user-level default.

    Priority: QUODEQ_EVALUATIONS_DIR env var > explicit *default* > ~/.quodeq/evaluations
    """
    from_env = os.environ.get("QUODEQ_EVALUATIONS_DIR")
    if from_env:
        return from_env
    if default is not None:
        return default
    return str(_DEFAULT_EVALUATIONS_DIR)


def get_anthropic_api_key() -> str | None:
    """Return the Anthropic API key from environment, or None."""
    return os.environ.get("ANTHROPIC_API_KEY") or None


def get_asvs_url() -> str:
    """Return the OWASP ASVS JSON URL from environment or default."""
    return os.environ.get("QUODEQ_ASVS_URL", _get_config()["asvs_url"])


def get_github_search_url() -> str:
    """Return the GitHub repository search URL from environment or default."""
    return os.environ.get("QUODEQ_GITHUB_SEARCH_URL", _get_config()["github_search_url"])


def get_github_raw_base_url() -> str:
    """Return the GitHub raw content base URL from environment or default."""
    return os.environ.get("QUODEQ_GITHUB_RAW_BASE_URL", _get_config()["github_raw_base_url"])


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
