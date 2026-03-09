"""Shared utilities, constants, and helpers for the Quodeq package."""
from __future__ import annotations

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
