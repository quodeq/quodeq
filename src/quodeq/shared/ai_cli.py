"""AI CLI subprocess runner for executing prompts via the configured AI command."""
from __future__ import annotations

import os
import subprocess

from quodeq.shared.utils import get_ai_cmd, sanitize_sensitive
_AI_CLI_FALLBACK_ERROR = (
    "AI command failed — check that the AI binary is installed, "
    "API key is set, and network is available"
)

_DEFAULT_AI_CLI_TIMEOUT = 300


def _ai_cli_timeout(override: int | None = None) -> int:
    """Return the AI CLI timeout in seconds. *override* bypasses env for testing."""
    if override is not None:
        return override
    raw = os.environ.get("QUODEQ_AI_CLI_TIMEOUT")
    if raw is None:
        return _DEFAULT_AI_CLI_TIMEOUT
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_AI_CLI_TIMEOUT


def run_ai_cli(prompt: str, *, timeout: int | None = None) -> tuple[str | None, str | None]:
    """Run the configured AI CLI with the given prompt and return (stdout, error)."""
    cmd = get_ai_cmd()
    try:
        result = subprocess.run(
            [cmd, "--print", "-p", prompt],
            check=True,
            capture_output=True,
            text=True,
            timeout=_ai_cli_timeout(timeout),
        )
    except FileNotFoundError:
        return None, f"AI command not found: {cmd}"
    except subprocess.CalledProcessError as exc:
        raw = exc.stderr.strip() if exc.stderr else ""
        return None, sanitize_sensitive(raw) or _AI_CLI_FALLBACK_ERROR
    except subprocess.TimeoutExpired:
        return None, "AI command timed out"

    return result.stdout, None
