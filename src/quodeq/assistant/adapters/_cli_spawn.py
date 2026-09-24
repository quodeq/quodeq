"""Hardened subprocess spawn for assistant CLI turns (read-only, scrubbed, scratch cwd)."""
from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable
from quodeq.config.provider import Provider
from quodeq.shared.constants import SYSTEM_DARWIN, SYSTEM_LINUX
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.copilot import build_copilot_env

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


def _shell_tool_disabled(argv: list[str]) -> bool:
    for i, token in enumerate(argv):
        if token in ("--disable=shell_tool", "features.shell_tool=false"):
            return True
        if token == "--disable" and i + 1 < len(argv) and argv[i + 1] == "shell_tool":
            return True
    return False


def _externally_sandboxed(argv: list[str]) -> bool:
    return bool(argv) and Path(argv[0]).name in _EXTERNAL_SANDBOX_LAUNCHERS


def build_chat_env(env: dict | None = None, *, provider: str | None = None) -> dict:
    source = resolve_env(env)
    if provider == Provider.COPILOT:
        return build_copilot_env(source)
    return {k: v for k, v in source.items() if k in _ALLOWED_ENV_KEYS or k.startswith("LC_")}


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


def _sb_quote(path: str) -> str:
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _seatbelt_profile(*, writable_dirs: list[str], writable_files: list[str]) -> str:
    """macOS Seatbelt (SBPL): allow reads/exec, deny all file writes except the
    scratch dir, system temp, ~/.codex state, and the assistant db files."""
    lines = ["(version 1)", "(allow default)", "(deny file-write*)", "(allow file-write*"]
    for d in ["/private/tmp", "/private/var/folders", *writable_dirs]:
        lines.append(f"  (subpath {_sb_quote(d)})")
    for f in writable_files:
        lines.append(f"  (literal {_sb_quote(f)})")
    lines.append('  (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr")'
                 ' (literal "/dev/dtracehelper") (subpath "/dev/fd"))')
    return "\n".join(lines) + "\n"


def _writable_paths(writable_dirs: list[str], writable_files: list[str]) -> list[str]:
    """Every path the sandbox must allow writes under.

    The writable dirs themselves, plus the parent of each writable file -- a
    sandbox grants a directory, not a single file.
    """
    return [*writable_dirs, *(str(Path(f).parent) for f in writable_files)]


def _bwrap_prefix(writable_dirs: list[str], writable_files: list[str]) -> list[str]:
    argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp", "--share-net", "--die-with-parent", "--unshare-pid"]
    seen: set[str] = set()
    for d in _writable_paths(writable_dirs, writable_files):
        if d and d not in seen:
            seen.add(d)
            argv += ["--bind", d, d]
    return argv


def external_sandbox_prefix(*, writable_dirs: list[str],
                            writable_files: list[str]) -> tuple[list[str], Callable[[], None]]:
    """Return (argv_prefix, cleanup) that wraps a command in an OS sandbox which
    allows reads + network but blocks file writes outside the given paths.

    Fails safe: raises if no sandbox mechanism is available on this platform, so
    codex never runs unsandboxed with its internal sandbox bypassed.
    """
    system = platform.system()
    if system == SYSTEM_DARWIN:
        profile = _seatbelt_profile(writable_dirs=writable_dirs, writable_files=writable_files)
        tmp = tempfile.NamedTemporaryFile("w", suffix=".sb", delete=False)
        tmp.write(profile)
        tmp.close()

        def _cleanup() -> None:
            Path(tmp.name).unlink(missing_ok=True)
        return ["sandbox-exec", "-f", tmp.name], _cleanup
    if system == SYSTEM_LINUX:
        if shutil.which("bwrap"):
            return _bwrap_prefix(writable_dirs, writable_files), lambda: None
        if shutil.which("firejail"):
            # firejail read-only whole fs, then allow-list the writable dirs
            argv = ["firejail", "--quiet", "--read-only=/"]
            for d in _writable_paths(writable_dirs, writable_files):
                argv.append(f"--read-write={d}")
            return argv, lambda: None
        raise RuntimeError(
            "Codex assistant turns require an OS sandbox (bubblewrap or firejail) "
            "which is not installed; install one, or use Claude/Gemini for the assistant.")
    raise RuntimeError(
        f"Codex assistant sandboxing is unsupported on {system}; use Claude/Gemini.")


def spawn_turn(argv: list[str], *, cwd: Path, env: dict) -> subprocess.Popen:
    assert_no_dangerous_args(argv)
    return subprocess.Popen(
        argv, cwd=str(cwd), env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", start_new_session=True,
    )
