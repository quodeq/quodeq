"""Git clone helpers for the filesystem action provider."""

from __future__ import annotations

import errno
import logging
import subprocess as _subprocess
from collections.abc import Mapping
from pathlib import Path

from quodeq.services.wiring import clone_repo, pinned_git_config, remove_clone_dir
from quodeq.config.clone_env import clone_shallow_months, git_clone_timeout_s
from quodeq.shared.git_errors import GitFailureKind, classify_git_output
from quodeq.shared.ssrf import resolve_addresses

_logger = logging.getLogger(__name__)

_KIND_NETWORK = GitFailureKind.NETWORK


class CloneError(RuntimeError):
    """Raised when git clone fails. ``kind`` is a ``GitFailureKind``.

    Inherits from RuntimeError so existing ``except RuntimeError`` blocks
    still catch it. ``retryable`` marks failures where a different clone
    strategy could still succeed (used for the shallow → full fallback).
    """

    def __init__(self, kind: GitFailureKind, message: str, stderr: str = "", *, retryable: bool = False) -> None:
        super().__init__(message)
        self.kind = kind
        self.stderr = stderr
        self.retryable = retryable


# Kinds where a shallow-specific rejection is indistinguishable from a real
# failure (servers answer unsatisfiable --shallow-since requests with generic
# hang-up/protocol errors), so a full clone may still succeed. Deterministic
# kinds (auth, not found, dest exists, disk) would fail identically.
_RETRYABLE_KINDS = (GitFailureKind.NETWORK, GitFailureKind.UNKNOWN)


def _pinned_git_config(url: str) -> list[str]:
    """``http.curloptResolve`` entries pinning git's connection to the
    addresses *url*'s host resolves to right now (see data/fs/git_pin.py).

    A host that does not resolve, or resolves to an internal address, is a
    NETWORK ``CloneError``. The resolver is this module's ``resolve_addresses``,
    the seam the clone tests replace.
    """
    try:
        return pinned_git_config(url, resolve=resolve_addresses)
    except ValueError as exc:
        raise CloneError(_KIND_NETWORK, str(exc)) from exc


def _clone_once(
    url: str, clone_dest: Path, extra_args: list[str], *, timeout_s: int | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    # The subprocess invocation lives in the data layer (ports.clone_repo);
    # this function owns mapping its raw failures onto CloneError kinds.
    resolved_timeout = timeout_s if timeout_s is not None else git_clone_timeout_s()
    git_config = _pinned_git_config(url)
    try:
        clone_repo(url, clone_dest, extra_args, timeout_s=resolved_timeout, git_config=git_config, env=env)
    except _subprocess.CalledProcessError as exc:
        raw = exc.stderr
        stderr = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else (raw or "")
        kind = classify_git_output(stderr)
        raise CloneError(
            kind, f"git clone failed ({kind})", stderr, retryable=kind in _RETRYABLE_KINDS,
        ) from exc
    except _subprocess.TimeoutExpired as exc:
        # Not retryable: the attempt already spent the whole clone timeout,
        # a full clone can only be slower.
        raise CloneError(GitFailureKind.TIMEOUT, "git clone timed out") from exc
    except FileNotFoundError as exc:
        raise CloneError(GitFailureKind.GIT_MISSING, f"git binary not found: {exc}") from exc
    except OSError as exc:
        kind = GitFailureKind.DISK if exc.errno == errno.ENOSPC else GitFailureKind.UNKNOWN
        raise CloneError(kind, f"git clone could not start: {exc}") from exc


def run_git_clone(
    url: str, clone_dest: Path, *, timeout_s: int | None = None, shallow_months: int | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Execute ``git clone`` for *url* into *clone_dest*. Raises CloneError on failure.

    An http(s) remote is cloned against the addresses its host resolves to
    at this moment (see ``_pinned_git_config``); a host that resolves to an
    internal address, or not at all, is refused before git starts.

    Clones shallow by default (``--single-branch``, ``--no-tags``,
    ``--shallow-since``): the working copy is evaluated at HEAD and the only
    history consumer is git churn scoring, whose lookback the default window
    covers (see ``config.clone_env.clone_shallow_months``). Branch evaluations
    against such a clone rely on ``_cli_worktree._fetch_branch`` fetching
    the missing branch on demand. Shallow requests the remote cannot satisfy
    (e.g. no commits inside the window) fall back to one full clone. A
    shallow working copy can be completed manually with ``git fetch
    --unshallow``.

    *timeout_s* and *shallow_months* default to the config-resolved values
    (each getter call is lazy, so env overrides set after import still apply).
    *env* is the base environment for the git process (``None`` means the
    process environment); the access ladder passes a token-carrying one.
    """
    months = shallow_months if shallow_months is not None else clone_shallow_months()
    if months <= 0:
        _clone_once(url, clone_dest, [], timeout_s=timeout_s, env=env)
        return
    try:
        _clone_once(
            url,
            clone_dest,
            ["--single-branch", "--no-tags", f"--shallow-since={months} months ago"],
            timeout_s=timeout_s,
            env=env,
        )
    except CloneError as exc:
        if not exc.retryable:
            raise
        _logger.info("shallow clone of %s failed (%s), retrying with full history", url, exc.kind)
        # git usually removes the dest it created on failure, but not when
        # killed or on checkout-phase errors; a leftover partial dir would
        # turn the retry into a bogus dest_exists failure.
        remove_clone_dir(clone_dest)
        _clone_once(url, clone_dest, [], timeout_s=timeout_s, env=env)
