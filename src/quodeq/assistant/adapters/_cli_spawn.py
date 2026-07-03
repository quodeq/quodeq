"""Hardened subprocess spawn for assistant CLI turns (read-only, scrubbed, scratch cwd)."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

# The spawned agent CLI is network-capable and tool-executing; it must NOT
# inherit arbitrary secrets from the server process (JIRA_API_TOKEN, GH_TOKEN,
# AWS_*, provider API keys, ...). Build the child env from an ALLOWLIST of the
# keys the CLI actually needs to run, rather than trying to enumerate every
# secret to deny. Provider auth vars (e.g. ANTHROPIC_API_KEY) are deliberately
# NOT allowed through: Claude Max uses its own login, and we treat API keys as
# sensitive by default.
_ALLOWED_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TERM", "TMPDIR", "TZ",
})
# Kept for readability/back-compat with anything still referencing the concept
# of "sensitive keys" conceptually; the allowlist above is what's enforced.
SENSITIVE_ENV_KEYS = frozenset({
    "QUODEQ_API_KEY", "DATABASE_URL", "SECRET_KEY",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
})

_DANGEROUS_VALUES = ("bypassPermissions",)
_DANGEROUS_FLAGS = (
    "--dangerously-bypass-approvals-and-sandbox",
    "--dangerously-skip-permissions",
    "--yolo",
)


def build_chat_env(env: dict | None = None) -> dict:
    source = env if env is not None else os.environ
    result = {k: v for k, v in source.items() if k in _ALLOWED_ENV_KEYS or k.startswith("LC_")}
    return result


def scratch_cwd(base: Path) -> Path:
    Path(base).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="assistant-scratch-", dir=str(base)))


def assert_no_dangerous_args(argv: list[str]) -> None:
    for token in argv:
        flag, _, value = token.partition("=")
        if token in _DANGEROUS_FLAGS or flag in _DANGEROUS_FLAGS:
            raise AssertionError(f"assistant spawn must never use {token!r}")
        if value in _DANGEROUS_VALUES or token in _DANGEROUS_VALUES:
            raise AssertionError(f"assistant spawn must never use {token!r}")


def spawn_turn(argv: list[str], *, cwd: Path, env: dict) -> subprocess.Popen:
    assert_no_dangerous_args(argv)
    return subprocess.Popen(
        argv, cwd=str(cwd), env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, start_new_session=True,
    )
