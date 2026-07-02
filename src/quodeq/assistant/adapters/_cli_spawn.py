"""Hardened subprocess spawn for assistant CLI turns (read-only, scrubbed, scratch cwd)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

SENSITIVE_ENV_KEYS = frozenset({
    "QUODEQ_API_KEY", "DATABASE_URL", "SECRET_KEY",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
})

_DANGEROUS = ("bypassPermissions", "--dangerously-bypass-approvals-and-sandbox", "--yolo")


def build_chat_env(env: dict | None = None) -> dict:
    result = dict(env if env is not None else os.environ)
    for key in SENSITIVE_ENV_KEYS:
        result.pop(key, None)
    return result


def scratch_cwd(base: Path) -> Path:
    cwd = Path(base) / "assistant-scratch"
    if cwd.exists():
        shutil.rmtree(cwd)
    cwd.mkdir(parents=True)
    return cwd


def assert_no_dangerous_args(argv: list[str]) -> None:
    for token in argv:
        candidates = [token, *token.split("=")]
        if any(c in _DANGEROUS for c in candidates):
            raise AssertionError(f"assistant spawn must never use {token!r}")


def spawn_turn(argv: list[str], *, cwd: Path, env: dict) -> subprocess.Popen:
    assert_no_dangerous_args(argv)
    return subprocess.Popen(
        argv, cwd=str(cwd), env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, start_new_session=True,
    )
