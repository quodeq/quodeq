"""Git CLI adapter — the single place that shells out to git.

services/_fs_scan, services/project_registration, shared/_repo and
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

from quodeq.shared._repo import normalize_remote_url

_logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 10


def run_git(
    args: Sequence[str], *, cwd: Path | str | None = None,
    timeout: float = _DEFAULT_TIMEOUT_S,
) -> str | None:
    """Run ``git *args`` and return stdout, or None on any failure."""
    try:
        result = subprocess.run(
            ["git", *args],
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
    UTF-8. Filtering on a half-answer would silently drop real source files
    from a run, so an unanswerable question has to leave the caller's file
    set exactly as it was.

    An empty index is treated as no answer too. A repository between ``git
    init`` and its first ``git add`` tracks nothing, and filtering on that
    would score zero files: no baseline exists yet to compare a working tree
    against, so the honest result is the unfiltered one the caller had
    before. A submodule's contents are not tracked by the parent repository,
    so they are absent here and are skipped — a submodule is its own
    repository and is listed by its own index.

    Each name is recorded in both unicode normalisations. git stores the
    bytes it was handed, while a filesystem may return a name composed
    differently (a repository written as NFC and checked out onto a
    normalising filesystem is the usual way the two diverge), and a
    byte-exact miss would silently drop a real source file. Keeping both
    spellings errs toward including a file, which is the safe direction.
    """
    try:
        out = run_git(["-C", str(path), "ls-files", "-z", "--cached"], timeout=timeout)
    except UnicodeDecodeError:
        # run_git decodes stdout as strict UTF-8; a tracked path with other
        # bytes in it is unreadable rather than absent, so do not filter.
        _logger.debug("Undecodable tracked path under %s", path)
        return None
    if out is None:
        return None
    rels = [rel for rel in out.split("\0") if rel]
    if not rels:
        _logger.info(
            "No tracked files under %s; scoring the working tree instead", path,
        )
        return None
    base = Path(path).resolve()
    return {
        base / spelling
        for rel in rels
        for spelling in {unicodedata.normalize("NFC", rel), unicodedata.normalize("NFD", rel)}
    }


def list_branches(repo_dir: Path, *, timeout: float = _DEFAULT_TIMEOUT_S) -> list[str]:
    """Local branch names of *repo_dir*; empty when not a git repo."""
    if not (repo_dir / ".git").exists():
        return []
    out = run_git(
        ["-C", str(repo_dir), "branch", "--format=%(refname:short)"],
        timeout=timeout,
    )
    if out is None:
        _logger.debug("Failed to list git branches for %s", repo_dir)
        return []
    return [b.strip() for b in out.splitlines() if b.strip()]


def remote_origin_url_raw(repo_dir: Path | str, *, timeout: float = _DEFAULT_TIMEOUT_S) -> str | None:
    """``git remote get-url origin`` verbatim, or None when absent/unreadable."""
    out = run_git(["-C", str(repo_dir), "remote", "get-url", "origin"], timeout=timeout)
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
        ["-C", repo_path, "config", "--get", "remote.origin.url"], timeout=timeout,
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
