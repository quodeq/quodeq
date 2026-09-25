"""Shared-repo git runner and cache paths: the base layer under
``shared_repo`` and ``shared_repo_meta``, which both import from here."""
from __future__ import annotations

import hashlib
import logging
import subprocess
from collections.abc import Mapping
from pathlib import Path

from quodeq.shared.constants import GIT_BIN
from quodeq.shared.env_paths import home_state_dir
from quodeq.shared.env_resolve import resolve_env

logger = logging.getLogger(__name__)

# Env var naming the cache root (the shared clones live under <root>/shared).
CACHE_ENV = "QUODEQ_CACHE_ROOT"
# Seconds; a first clone of a results repo can legitimately take minutes.
DEFAULT_GIT_TIMEOUT_S = 300
EVALUATIONS_DIRNAME = "evaluations"  # the clone's evaluations/ tree; see shared_evaluations_root


def git_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment for git subprocess calls, layered over *env*.

    GIT_LFS_SKIP_SMUDGE avoids pulling LFS blobs we don't need. GIT_TERMINAL_PROMPT=0
    stops git from blocking on an interactive credential or passphrase prompt, since
    these subprocess calls have stdin closed (see run_git) and nobody is there to answer.

    Known limitation: GIT_TERMINAL_PROMPT only covers prompts issued by git
    itself. ssh reads from /dev/tty directly, so a first-contact host-key
    confirmation or a key passphrase without a loaded agent still blocks, and
    the call only dies at the run_git timeout. ssh remotes need the host in
    known_hosts and the key in an agent (or use an https remote instead).
    """
    return {**resolve_env(env), "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"}


def run_git(
    args: list[str], *, cwd: Path | None = None, timeout: int = DEFAULT_GIT_TIMEOUT_S,
    env: Mapping[str, str] | None = None,
) -> tuple[bool, str]:
    """Run a git command and return ``(ok, output)``.

    *output* is the merged stdout+stderr of a git command that actually ran,
    which is safe to surface to a caller. A process that never ran (git
    missing, the timeout fired) is logged server-side and reported as a
    generic reason instead, since its exception text can carry local paths and
    errno detail. Never raises. stdin is closed, so git can never block on a
    prompt.
    """
    try:
        proc = subprocess.run(
            [GIT_BIN, *args],
            cwd=str(cwd) if cwd else None,
            env=git_env(env),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        # Unlike a failed git command (whose stdout/stderr is safe, expected
        # user-facing text -- see refresh_shared_clone's docstring), this
        # branch only fires for process-launch failures (git missing, a
        # timeout). str(exc) there can include local details (the resolved
        # command line, filesystem errno text) that callers surface straight
        # into HTTP error responses, so keep it out of the returned reason
        # and log it server-side instead.
        logger.warning("run_git: %s failed to launch/complete: %s", args, exc)
        return False, "git command failed to run"


def shared_cache_base(env: Mapping[str, str] | None = None) -> Path:
    """Root of every shared-repo cache: ``$QUODEQ_CACHE_ROOT/shared`` or ``~/.quodeq/cache/shared``."""
    e = resolve_env(env)
    base = e.get(CACHE_ENV)
    root = Path(base) if base else home_state_dir() / "cache"
    return root / "shared"


def shared_cache_dir(url: str, env: Mapping[str, str] | None = None) -> Path:
    """Per-remote cache directory, named by a 16-char digest of *url*."""
    digest = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]
    return shared_cache_base(env) / digest


def shared_repo_path(url: str, env: Mapping[str, str] | None = None) -> Path:
    """Clone directory for *url*. Also the key ``clone_lock`` locks on."""
    return shared_cache_dir(url, env) / "repo"


def shared_evaluations_root(url: str, env: Mapping[str, str] | None = None) -> Path:
    """The clone's evaluations/ tree, laid out like the local evaluations dir."""
    return shared_repo_path(url, env) / EVALUATIONS_DIRNAME
