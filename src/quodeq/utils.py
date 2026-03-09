"""Shared utilities, constants, and helpers for the Quodeq package."""
from __future__ import annotations

import json
from pathlib import Path

# Shared default for the AI CLI command name (used by ai_cli.py and engine/analysis.py).
AI_CMD_DEFAULT = "claude"

# Anthropic API configuration
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_API_VERSION = "2023-06-01"

# Server defaults
ACTION_API_PORT = 8001
ACTION_API_MODULE = "quodeq.action_api"


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


def get_ai_cmd() -> str:
    """Return the AI CLI command from environment or default."""
    import os
    return os.environ.get("AI_CMD", AI_CMD_DEFAULT)


def get_ai_model() -> str | None:
    """Return the AI model from environment, or None."""
    import os
    return os.environ.get("AI_MODEL") or None


def get_action_api_port() -> int:
    """Return the action API port from environment or default."""
    import os
    return int(os.environ.get("QUODEQ_ACTION_API_PORT", str(ACTION_API_PORT)))


def get_action_api_host() -> str:
    """Return the action API host from environment or default."""
    import os
    return os.environ.get("QUODEQ_ACTION_API_HOST", "127.0.0.1")


def get_static_dist() -> str | None:
    """Return the static dist path from environment, or None."""
    import os
    return os.environ.get("QUODEQ_STATIC_DIST")


def get_evaluations_dir(default: str = "evaluations") -> str:
    """Return the evaluations directory from environment or default."""
    import os
    return os.environ.get("QUODEQ_EVALUATIONS_DIR", default)
