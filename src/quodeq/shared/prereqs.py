"""Prerequisite checks for external tool dependencies."""
from __future__ import annotations

import os
import subprocess
import urllib.error
import urllib.request

from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.shared.utils import IS_WIN32 as _IS_WIN32, get_ai_cmd

_INSTALL_HINT_NODE = (
    "Install it from https://nodejs.org/ or via your package manager:\n"
    "  brew install node        # macOS\n"
    "  apt install nodejs       # Ubuntu/Debian"
)

_CLI_INSTALL_HINTS: dict[str, str] = {
    "claude": (
        "Install Claude Code:\n"
        "  npm install -g @anthropic-ai/claude-code\n"
        "  https://docs.anthropic.com/en/docs/claude-code/overview"
    ),
    "codex": (
        "Install Codex CLI:\n"
        "  npm install -g @openai/codex\n"
        "  https://developers.openai.com/codex/quickstart"
    ),
    "gemini": (
        "Install Gemini CLI:\n"
        "  npm install -g @anthropic-ai/gemini-cli\n"
        "  https://geminicli.com/docs/get-started/installation/"
    ),
}

_SETTINGS_HINT = (
    "Open the dashboard and go to Settings to select your AI provider:\n"
    "  quodeq"
)

_VERSION_CMD_TIMEOUT_S = 30


def _run_version_cmd(cmd: list[str]) -> str:
    """Run a command and return its stdout, or raise FileNotFoundError.

    ``shell=True`` is required on Windows so that ``where`` and other
    shell built-ins resolve correctly.  The *cmd* list is always
    hard-coded by callers in this module (never user-influenced),
    so the shell injection risk does not apply.

    SECURITY: Do not pass user-controlled strings into *cmd*.
    """
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True, shell=_IS_WIN32,
        timeout=_VERSION_CMD_TIMEOUT_S,
    )
    return result.stdout.strip()


def _parse_major(version_str: str) -> int:
    """Extract the major version number from a version string like 'v20.11.0' or '10.2.0'."""
    cleaned = version_str.lstrip("v")
    return int(cleaned.split(".")[0])


def _check_tool_version(cmd: list[str], tool_name: str, min_major: int, install_hint: str) -> None:
    """Raise RuntimeError if *tool_name* is missing or below *min_major*."""
    try:
        version_str = _run_version_cmd(cmd)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"{tool_name} {min_major}+ is required but not found.\n{install_hint}"
        ) from exc
    try:
        major = _parse_major(version_str)
    except (ValueError, IndexError):
        return
    if major < min_major:
        raise RuntimeError(
            f"{tool_name} {version_str} is below the minimum required version {min_major}.x.\n"
            f"{install_hint}"
        )


def check_node(min_major: int = 18) -> None:
    """Raise RuntimeError if Node.js is missing or below minimum version."""
    _check_tool_version(["node", "--version"], "Node.js", min_major, _INSTALL_HINT_NODE)


def check_npm(min_major: int = 9) -> None:
    """Raise RuntimeError if npm is missing or below minimum version."""
    _check_tool_version(["npm", "--version"], "npm", min_major, _INSTALL_HINT_NODE)


def _is_provider_explicitly_configured() -> bool:
    """Return True if the user has explicitly set a provider via env or config."""
    return "AI_PROVIDER" in os.environ or "AI_CMD" in os.environ


def _check_cli_provider(provider: str) -> None:
    """Check that a CLI provider binary is available on PATH."""
    try:
        _run_version_cmd([provider, "--version"])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        hint = _CLI_INSTALL_HINTS.get(provider, f"Install {provider} and make sure it is on your PATH.")
        raise RuntimeError(
            f"'{provider}' is configured as your AI provider but was not found.\n\n"
            f"{hint}\n\n"
            f"Or choose a different provider in the dashboard Settings:\n"
            f"  quodeq"
        ) from exc


def _check_api_provider(provider: str) -> None:
    """Check that an API provider has basic connectivity (Ollama: server running)."""
    if provider == "ollama":
        try:
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(
                "Ollama is configured as your AI provider but the server is not running.\n\n"
                "Start it with:\n"
                "  ollama serve\n\n"
                "Or install Ollama from https://ollama.com/download"
            ) from exc


def check_dashboard_prereqs() -> None:
    """Check all prerequisites for the dashboard command."""
    check_node()
    check_npm()


def check_evaluate_prereqs() -> None:
    """Check all prerequisites for the evaluate command.

    Checks the configured AI provider instead of always assuming Claude.
    If no provider is configured, tells the user to select one.
    """
    if not _is_provider_explicitly_configured():
        raise RuntimeError(
            "No AI provider configured.\n\n"
            "Quodeq needs an AI provider to evaluate your code. You can use:\n\n"
            "  Local (free, private):  Ollama with Gemma 4\n"
            "  Cloud (faster):         Claude Code, Codex CLI, or Gemini CLI\n\n"
            f"{_SETTINGS_HINT}"
        )

    provider = get_ai_cmd()
    configs = get_provider_configs()
    provider_cfg = configs.get(provider, {})
    provider_type = provider_cfg.get("type", "cli")

    if provider_type == "cli":
        _check_cli_provider(provider)
    elif provider_type == "api":
        _check_api_provider(provider)
