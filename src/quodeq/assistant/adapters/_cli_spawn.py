"""Hardened subprocess spawn for assistant CLI turns (read-only, scrubbed, scratch cwd)."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from quodeq.config.provider import Provider
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.codex_home import dedicated_codex_home, provider_env_keys
from quodeq.shared.copilot import build_copilot_env
from quodeq.shared.os_sandbox import external_sandbox_prefix  # noqa: F401 -- re-export

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
_DANGEROUS_VALUES = ("bypassPermissions",)
# Permission-skip flags that are NEVER acceptable in an assistant spawn.
_DANGEROUS_FLAGS = (
    "--dangerously-skip-permissions",
    "--yolo",
)
# codex cancels every MCP tool call under its OWN sandbox, so it must run with
# `--dangerously-bypass-approvals-and-sandbox`. We make that safe by (a) removing
# its shell tool and (b) wrapping the process in an OS sandbox WE control (see
# external_sandbox_prefix) that blocks file writes outside the scratch/temp/db.
# This flag is therefore permitted ONLY when both conditions hold in the argv.
_BYPASS_SANDBOX_FLAG = "--dangerously-bypass-approvals-and-sandbox"
_EXTERNAL_SANDBOX_LAUNCHERS = ("sandbox-exec", "bwrap", "firejail")
_FLAG_DISABLE = "--disable"
_SHELL_TOOL_ARG = "shell_tool"
_FLAG_DISABLE_SHELL_TOOL_EQ = "--disable=shell_tool"  # codex: single-token disable spelling
_CONFIG_SHELL_TOOL_FALSE = "features.shell_tool=false"  # codex: config-override disable spelling


def _shell_tool_disabled(argv: list[str]) -> bool:
    for i, token in enumerate(argv):
        if token in (_FLAG_DISABLE_SHELL_TOOL_EQ, _CONFIG_SHELL_TOOL_FALSE):
            return True
        if token == _FLAG_DISABLE and i + 1 < len(argv) and argv[i + 1] == _SHELL_TOOL_ARG:
            return True
    return False


def _externally_sandboxed(argv: list[str]) -> bool:
    return bool(argv) and Path(argv[0]).name in _EXTERNAL_SANDBOX_LAUNCHERS


def build_chat_env(env: dict | None = None, *, provider: str | None = None) -> dict:
    source = resolve_env(env)
    if provider == Provider.COPILOT:
        return build_copilot_env(source)
    env = {k: v for k, v in source.items() if k in _ALLOWED_ENV_KEYS or k.startswith("LC_")}
    if provider == Provider.CODEX:
        # Not the user's ~/.codex: its MCP servers, plugins and the ChatGPT
        # account apps would load even with the shell tool disabled.
        env["CODEX_HOME"] = str(dedicated_codex_home(source))
        env.update({k: source[k] for k in provider_env_keys(source) if k in source})
    return env


def scratch_cwd(base: Path) -> Path:
    Path(base).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="assistant-scratch-", dir=str(base)))


def assert_no_dangerous_args(argv: list[str]) -> None:
    bypass_ok = _shell_tool_disabled(argv) and _externally_sandboxed(argv)
    for token in argv:
        flag, _, value = token.partition("=")
        if token == _BYPASS_SANDBOX_FLAG or flag == _BYPASS_SANDBOX_FLAG:
            if bypass_ok:
                continue  # MCP-only codex inside an OS sandbox we control
            raise AssertionError(
                f"assistant spawn must never use {token!r} without --disable "
                "shell_tool AND an external OS sandbox wrapper")
        if token in _DANGEROUS_FLAGS or flag in _DANGEROUS_FLAGS:
            raise AssertionError(f"assistant spawn must never use {token!r}")
        if value in _DANGEROUS_VALUES or token in _DANGEROUS_VALUES:
            raise AssertionError(f"assistant spawn must never use {token!r}")


def mcp_arg_dirs(args: list[str]) -> list[str]:
    """The absolute paths among the MCP server's args (repo root, run and
    reports dirs, ...), as dirs: a file's parent, since the sandbox grants dirs."""
    paths = []
    for arg in args:
        if arg.startswith("/"):
            path = Path(arg)
            paths.append(str(path if path.is_dir() else path.parent))
    return paths


def spawn_turn(argv: list[str], *, cwd: Path, env: dict) -> subprocess.Popen:
    assert_no_dangerous_args(argv)
    return subprocess.Popen(
        argv, cwd=str(cwd), env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", start_new_session=True,
    )
