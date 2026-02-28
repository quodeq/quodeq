from __future__ import annotations

import subprocess

from codecompass.evaluate.lib.ai_cli_provider import get_ai_cmd


def run_ai_cli(prompt: str) -> tuple[str | None, str | None]:
    cmd = get_ai_cmd()
    try:
        result = subprocess.run(
            [cmd, "--print", "-p", prompt],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None, f"AI command not found: {cmd}"
    except subprocess.CalledProcessError as exc:
        return None, exc.stderr.strip() or "AI command failed"

    return result.stdout, None
