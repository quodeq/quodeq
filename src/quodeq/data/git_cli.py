"""Git CLI adapter — the single place that shells out to git.

services/fs_scan, services/project_registration, shared/_repo and
analysis/subagents/_git_scoring used to run subprocess directly, coupling
business flows to process execution. Every helper here is best-effort:
missing git, non-repo directories, timeouts and failures yield None or
empty results, matching the callers' long-standing behavior.
"""
from __future__ import annotations

import logging
import subprocess
import unicodedata
from collections.abc import Iterator, Sequence
from pathlib import Path

from quodeq.shared.constants import GIT_BIN, GIT_DIR_NAME, GIT_FLAG_C
from quodeq.shared.repo import normalize_remote_url

_logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 10


def run_git(
    args: Sequence[str], *, cwd: Path | str | None = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> str | None:
    """Run ``git *args`` and return stdout, or None on any failure."""
    try:
        result = subprocess.run(
            [GIT_BIN, *args],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def list_tracked_files(
    path: Path | str, *, timeout: float = _DEFAULT_TIMEOUT_S,
) -> set[Path] | None:
    """Absolute paths of the files git tracks at or under *path*, or None.

    Runs ``git ls-files -z --cached`` with *path* as the working directory,
    which restricts the listing to that subtree and reports every path
    relative to it, so the result is rebuilt as ``path.resolve() / rel`` and
    needs no knowledge of where the repository root sits. ``--cached`` counts
    a staged-but-uncommitted file as tracked. ``-z`` is not optional: git's
    default output C-quotes any name holding a space, a quote or a non-ASCII
    byte (``"h\\303\\251llo.py"``), so only the NUL-separated form can be
    split back into real paths.

    None means "no answer, do not filter" and is returned for every failure
    mode: *path* is outside a git work tree, the ``git`` binary is missing,
    the command exits non-zero, it times out, or a tracked path is not valid
    UTF-8. Filtering on a half-answer would silently drop real source files,
    so an unanswerable question leaves the caller's set as it was.

    An empty listing is two different situations and they get opposite
    answers. A repository whose index is empty, between ``git init`` and its
    first ``git add``, has no baseline to filter against, so it answers None
    and the working tree is scanned as before. A repository that tracks
    files elsewhere but none under *path*, a gitignored ``vendor`` tree for
    instance, answers an empty set: nothing there belongs to the codebase,
    and scoring zero files is the correct result rather than a fallback.
    Telling them apart costs one extra listing, only when the first is
    empty. A submodule's contents are not in the parent index, so they are
    skipped; a submodule is its own repository with its own index.

    Each name is recorded in both unicode normalisations, because git stores
    the bytes it was handed while a filesystem may compose a name
    differently, and a byte-exact miss would drop a real file silently.
    Mixed-form paths and case-only divergence are still misses.
    """
    rels = _tracked_rels(path, [], timeout)
    if rels is None:
        return None
    if not rels:
        whole_repo = _tracked_rels(path, ["--", ":/"], timeout)
        if whole_repo is None or not whole_repo:
            _logger.info("Nothing tracked in %s; scoring the working tree", path)
            return None
        return set()
    base = Path(path).resolve()
    return {
        base / spelling
        for rel in rels
        for spelling in {unicodedata.normalize("NFC", rel), unicodedata.normalize("NFD", rel)}
    }


def _tracked_rels(
    path: Path | str, pathspec: list[str], timeout: float,
) -> list[str] | None:
    """Tracked paths as git reports them, or None when it cannot answer."""
    try:
        out = run_git(
            [GIT_FLAG_C, str(path), "ls-files", "-z", "--cached", *pathspec], timeout=timeout,
        )
    except UnicodeDecodeError:
        # run_git decodes stdout as strict UTF-8; a tracked path carrying
        # other bytes is unreadable rather than absent, so do not filter.
        _logger.debug("Undecodable tracked path under %s", path)
        return None
    if out is None:
        return None
    return [rel for rel in out.split("\0") if rel]


def list_branches(repo_dir: Path, *, timeout: float = _DEFAULT_TIMEOUT_S) -> list[str]:
    """Local branch names of *repo_dir*; empty when not a git repo."""
    if not (repo_dir / GIT_DIR_NAME).exists():
        return []
    out = run_git(
        [GIT_FLAG_C, str(repo_dir), "branch", "--format=%(refname:short)"],
        timeout=timeout,
    )
    if out is None:
        _logger.debug("Failed to list git branches for %s", repo_dir)
        return []
    return [b.strip() for b in out.splitlines() if b.strip()]


def remote_origin_url_raw(repo_dir: Path | str, *, timeout: float = _DEFAULT_TIMEOUT_S) -> str | None:
    """``git remote get-url origin`` verbatim, or None when absent/unreadable."""
    out = run_git([GIT_FLAG_C, str(repo_dir), "remote", "get-url", "origin"], timeout=timeout)
    if out is None:
        return None
    origin = out.strip()
    return origin or None


def git_remote_url(repo_path: str, *, timeout: float = _DEFAULT_TIMEOUT_S) -> str | None:
    """Normalized canonical URL of the git 'origin' remote, if any.

    Reads ``git config --get remote.origin.url`` and folds equivalent forms
    (https / ssh:// / git@host:path, with or without ``.git``) into
    ``host/owner/repo`` via ``shared._repo.normalize_remote_url``.
    """
    out = run_git(
        [GIT_FLAG_C, repo_path, "config", "--get", "remote.origin.url"], timeout=timeout,
    )
    if out is None:
        return None
    return normalize_remote_url(out)


def stream_log_names(
    repo_dir: Path, *, months: int = 3, timeout: float = _DEFAULT_TIMEOUT_S,
) -> Iterator[str]:
    """Yield ``git log --name-only`` lines one at a time (streaming Popen).

    Avoids materializing the full log for large repositories. Yields
    nothing when git is unavailable or the command cannot start.
    """
    try:
        proc = subprocess.Popen(
            ["git", "log", f"--since={months} months ago", "--name-only", "--format=%H%n%ai"],
            cwd=str(repo_dir), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8",
        )
    except OSError:
        return
    try:
        assert proc.stdout is not None
        yield from proc.stdout
    finally:
        proc.stdout.close()  # type: ignore[union-attr]
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
