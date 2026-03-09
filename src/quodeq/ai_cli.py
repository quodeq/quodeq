from __future__ import annotations

import os
import subprocess

_AI_CLI_TIMEOUT_S = 300


def run_ai_cli(prompt: str) -> tuple[str | None, str | None]:
    cmd = os.environ.get("AI_CMD", "claude")
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
