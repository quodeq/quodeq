"""AI CLI ``/models`` discovery adapter — the process boundary for CLI model listing.

``services/tooling_mixin.py`` owns the policy (client allowlist, isalnum
guard, output-token parsing); this module owns the process boundary: is the
binary installed, run it, and hand back raw stdout. Mirrors how
``data/fs/repo_clone.py`` wraps git behind ``ports.clone_repo``.
"""
from __future__ import annotations

import shutil
import subprocess


def run_cli_models_command(client_id: str, *, timeout_s: float) -> str:
    """Run ``<client_id> /models`` and return its stdout, or "" on any failure.

    "" covers: the binary is not installed, it times out, it exits non-zero,
    or the process cannot be started at all.
    """
    if not shutil.which(client_id):
        return ""
    try:
        result = subprocess.run(
            [client_id, "/models"],
            capture_output=True,
            text=True, encoding="utf-8",
            timeout=timeout_s,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return result.stdout if result.returncode == 0 else ""
