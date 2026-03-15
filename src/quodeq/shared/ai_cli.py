"""AI CLI subprocess runner for executing prompts via the configured AI command."""
from __future__ import annotations

import os
import re
import subprocess

from quodeq.shared.utils import get_ai_cmd

_SENSITIVE_PATTERNS = re.compile(
    r"(api[_-]?key|token|secret|password|authorization)[=:\s]+\S+",
    re.IGNORECASE,
)

def _ai_cli_timeout() -> int:
    """Return the AI CLI timeout in seconds (reads env at call time)."""
    return int(os.environ.get("QUODEQ_AI_CLI_TIMEOUT", "300"))


def run_ai_cli(prompt: str) -> tuple[str | None, str | None]:
    """Run the configured AI CLI with the given prompt and return (stdout, error)."""
    cmd = get_ai_cmd()
    try:
        result = subprocess.run(
            [cmd, "--print", "-p", prompt],
            check=True,
            capture_output=True,
            text=True,
            timeout=_ai_cli_timeout(),
        )
    except FileNotFoundError:
        return None, f"AI command not found: {cmd}"
    except subprocess.CalledProcessError as exc:
        raw = exc.stderr.strip() if exc.stderr else ""
        return None, _SENSITIVE_PATTERNS.sub(r"\1=***", raw) or "AI command failed — check that the AI binary is installed, API key is set, and network is available"
    except subprocess.TimeoutExpired:
        return None, "AI command timed out"

    return result.stdout, None
