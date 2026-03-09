"""AI CLI subprocess runner for executing prompts via the configured AI command."""
from __future__ import annotations

import subprocess

from quodeq.utils import get_ai_cmd

_AI_CLI_TIMEOUT_S = 300


def run_ai_cli(prompt: str) -> tuple[str | None, str | None]:
    """Run the configured AI CLI with the given prompt and return (stdout, error)."""
    cmd = get_ai_cmd()
    try:
        result = subprocess.run(
            [cmd, "--print", "-p", prompt],
            check=True,
            capture_output=True,
            text=True,
            timeout=_AI_CLI_TIMEOUT_S,
        )
    except FileNotFoundError:
        return None, f"AI command not found: {cmd}"
    except subprocess.CalledProcessError as exc:
        return None, exc.stderr.strip() or "AI command failed"
    except subprocess.TimeoutExpired:
        return None, "AI command timed out"

    return result.stdout, None
