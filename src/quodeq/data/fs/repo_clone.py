"""Repository cloning and cleanup — manages clone directories.

Online repos are cached under ``~/.quodeq/cache/online/<url_hash>/repo``
via :mod:`quodeq.context.online_cache`, so subsequent evaluations against
the same URL reuse the working copy (fetch + reset) instead of re-cloning
into a fresh temp dir. Set ``QUODEQ_DISABLE_ONLINE_CACHE=1`` to fall back
to the legacy mkdtemp flow (one fresh clone per evaluation).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from quodeq.context.online_cache import (
    cache_disabled,
    ensure_clone,
    is_inside_cache,
)
from quodeq.data.fs.git_stream import run_git_streaming
from quodeq.data.git_cli import git_env_floor
from quodeq.data.fs.repo_validation import validate_remote_url as _validate_remote_url
from quodeq.config.clone_env import git_clone_timeout_s

_logger = logging.getLogger(__name__)


def _clone_args(url: str, dest: Path, extra_args: list[str], git_config: Sequence[str]) -> list[str]:
    """The ``git clone`` argv after the binary; one shape for the buffered and streaming paths."""
    config_flags = [flag for entry in git_config for flag in ("-c", entry)]
    return [*config_flags, "clone", "--progress", *extra_args, "--", url, str(dest)]


class GitCloneClient:
    """The external ``git clone`` process boundary.

    Two call shapes, kept deliberately distinct rather than collapsed into
    one: ``clone_progress`` is the interactive/services path (pinned locale
    so stderr carries English markers callers classify on, ``capture_output``
    so that stderr is available to inspect, and a ``--`` separator before the
    URL — an argument-injection guard for a URL that could start with ``-``).
    ``clone_legacy`` is the plain mkdtemp fallback and has neither: it
    streams output straight through and never received untrusted
    dash-prefixed input in practice. Do not unify the two argv shapes.

    *env* is the base environment both clones inherit; ``None`` means the
    process environment, read when the clone runs.
    """

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env = env

    def clone_progress(
        self, url: str, dest: Path, extra_args: list[str], *, timeout_s: int,
        git_config: Sequence[str] = (),
    ) -> None:
        """Run ``git clone`` for *url* into *dest*.

        *git_config* entries (``key=value``) apply to this git process only,
        via the global ``-c`` flag; they are not written into the clone.

        Raises the raw ``subprocess`` / ``OSError`` failures unchanged — the
        services layer owns retry orchestration and mapping them to
        user-facing clone errors.
        """
        subprocess.run(
            ["git", *_clone_args(url, dest, extra_args, git_config)],
            check=True,
            env=git_env_floor(self._env),
            stdin=subprocess.DEVNULL,
            timeout=timeout_s,
            capture_output=True,
        )

    def clone_streaming(
        self, url: str, dest: Path, extra_args: list[str], *, timeout_s: int,
        git_config: Sequence[str] = (), on_line: Callable[[str], None],
    ) -> tuple[bool, str]:
        """``clone_progress`` with every stderr line handed to *on_line* as it arrives.

        Same argv and guards as ``clone_progress`` (pinned locale via
        ``git_env_floor``, closed stdin, ``--`` before the URL); returns the
        runner's ``(ok, tail)`` instead of raising, so the caller classifies.
        """
        return run_git_streaming(
            _clone_args(url, dest, extra_args, git_config),
            timeout=timeout_s, env=git_env_floor(self._env), on_line=on_line,
        )

    def clone_legacy(self, repo_input: str, dest: Path, *, timeout_s: int) -> None:
        """Run ``git clone`` for *repo_input* into *dest* (mkdtemp fallback path)."""
        env = git_env_floor(self._env)
        subprocess.run(
            ["git", "clone", "--progress", repo_input, str(dest)],
            check=True, env=env, stdin=subprocess.DEVNULL, timeout=timeout_s,
        )


_default_git_client = GitCloneClient()


@dataclass(frozen=True)
class OnlineCacheOps:
    """Online-cache collaborators ``prepare_repository`` drives. None =
    production default (``context.online_cache.cache_disabled``/
    ``ensure_clone``). The cache's own clone/fetch internals are not
    threaded here -- only the two calls this module makes directly."""

    cache_disabled: Callable[[], bool] | None = None
    ensure_clone: Callable[[str], Path | None] | None = None


def clone_repo(
    url: str, dest: Path, extra_args: list[str], *, timeout_s: int,
    git_config: Sequence[str] = (), env: Mapping[str, str] | None = None,
) -> None:
    """Compat wrapper around :meth:`GitCloneClient.clone_progress`. See that
    method for the argv-shape rationale. *env* (None = process environment)
    is the base environment the clone inherits; a non-None value builds a
    one-off client instead of using the module default.
    """
    client = _default_git_client if env is None else GitCloneClient(env)
    client.clone_progress(url, dest, extra_args, timeout_s=timeout_s, git_config=git_config)


def _legacy_tempdir_clone(repo_input: str, *, client: GitCloneClient | None = None) -> str:
    """Fall-back path: fresh ``mkdtemp`` + ``git clone`` every call.

    Used when the online cache is disabled or when the cache helper
    couldn't produce a working copy (e.g. the cache directory is read-only).
    """
    client = client or _default_git_client
    # rstrip("/") + fallback: a trailing-slash URL yields an empty basename,
    # which would make dest the mkdtemp dir itself — and cleanup_cloned_repo
    # removes dest's *parent*, i.e. the system temp root.
    repo_name = repo_input.rstrip("/").split("/")[-1].removesuffix(".git") or "repo"
    tmp_dir = tempfile.mkdtemp()
    dest = Path(tmp_dir) / repo_name
    try:
        timeout_s = git_clone_timeout_s()
        _logger.info("Cloning %s (timeout: %ds)...", repo_input, timeout_s)
        client.clone_legacy(repo_input, dest, timeout_s=timeout_s)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return str(dest.resolve())


def prepare_repository(
    repo_input: str, *, client: GitCloneClient | None = None,
    cache_ops: OnlineCacheOps | None = None,
) -> str:
    """Return a local working copy of *repo_input*, cloning if necessary.

    Routes through :func:`quodeq.context.online_cache.ensure_clone` so the
    second-and-onward evaluations of the same URL reuse a shallow cached
    clone (fetched + reset to ``origin/HEAD``). The legacy mkdtemp clone
    path is kept as a fallback and behind ``QUODEQ_DISABLE_ONLINE_CACHE``.
    *client* is an injection seam for the legacy path only. *cache_ops* is
    an :class:`OnlineCacheOps` bundle for the two online-cache calls this
    function makes directly — the online cache's own clone/fetch internals
    are a separate collaborator, not threaded here.

    Raises ValueError if the URL does not match the expected git
    repository format.
    """
    ops = cache_ops or OnlineCacheOps()
    is_cache_disabled = ops.cache_disabled if ops.cache_disabled is not None else cache_disabled
    do_ensure_clone = ops.ensure_clone if ops.ensure_clone is not None else ensure_clone
    _validate_remote_url(repo_input)
    if is_cache_disabled():
        return _legacy_tempdir_clone(repo_input, client=client)
    cached = do_ensure_clone(repo_input)
    if cached is not None:
        return str(cached.resolve())
    # Cache-miss + clone failure: try the old path so a corrupt cache
    # entry doesn't take an entire evaluation offline.
    return _legacy_tempdir_clone(repo_input, client=client)


def cleanup_cloned_repo(repo_path: str) -> None:
    """Remove the temporary clone directory for *repo_path*.

    No-op when *repo_path* lives inside the persistent online cache:
    that dir survives between evaluations on purpose. Only the legacy
    mkdtemp clones get torn down here.
    """
    if is_inside_cache(repo_path):
        return
    temp_root = Path(tempfile.gettempdir()).resolve()
    resolved = Path(repo_path).resolve()
    target = resolved.parent
    if target == temp_root or not target.is_relative_to(temp_root):
        # Defense-in-depth: never remove the system temp root or anything
        # outside it. When dest sits directly inside the temp root (e.g. an
        # empty repo name made dest the mkdtemp dir itself), fall back to
        # removing just the clone.
        if resolved != temp_root and resolved.is_relative_to(temp_root):
            target = resolved
        else:
            _logger.warning("Refusing to clean up %s: not inside the temp dir", repo_path)
            return
    try:
        # No ignore_errors=True: it would swallow the OSError and make the
        # warning below unreachable. Let rmtree raise so the failure is logged.
        shutil.rmtree(str(target))
    except OSError as exc:
        _logger.warning("Failed to clean up temp repo dir %s: %s", target, exc)
