"""Find a repo's credential files on disk (see ``core.secret_files``)."""
from __future__ import annotations

import functools
import logging
import os
import time
from pathlib import Path

from quodeq.core.secret_files import secret_file_kind
from quodeq.data.git_cli import list_tracked_files

_logger = logging.getLogger(__name__)

# Installed dependencies and tool caches: other people's files, often huge.
_SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__",
                        ".tox", ".mypy_cache", ".pytest_cache"})
# Each one becomes a sandbox rule; past this the walk stops and says so.
MAX_SECRET_FILES = 500
_MAX_READ_BYTES = 256 * 1024
# Every agent of a run asks for the same repo; one walk serves them all.
_WALK_CACHE_S = 60
_WALK_CACHE_REPOS = 8  # concurrent runs on different repos


def find_secret_files(root: Path, *, limit: int = MAX_SECRET_FILES) -> list[Path]:
    """Every credential file under *root*, tracked or not, for a sandbox to
    deny. A symlinked one is listed with its target, since a sandbox may
    check either. Symlinked directories are not followed. The answer is
    reused for up to a minute."""
    return list(_walk(str(root), limit, int(time.monotonic() // _WALK_CACHE_S)))


@functools.lru_cache(maxsize=_WALK_CACHE_REPOS)
def _walk(root: str, limit: int, _window: int) -> tuple[Path, ...]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _exc: None):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if secret_file_kind(name) is None:
                continue
            path = Path(dirpath) / name
            found.append(path)
            if path.is_symlink():
                found.append(path.resolve())
            if len(found) >= limit:
                _logger.warning("secret files: stopped at %d under %s", limit, root)
                return tuple(found)
    return tuple(found)


def read_tracked_secret_files(root: Path) -> list[tuple[str, str, str]]:
    """``(repo-relative posix path, kind, text)`` for each credential file git
    tracks under *root*. Untracked ones (a gitignored ``.env``) are where
    credentials belong, so they are left out; so is everything when git
    cannot answer. Symlinks are skipped: their content is not the repo's."""
    tracked = list_tracked_files(root)
    if not tracked:
        return []
    base = root.resolve()
    out: list[tuple[str, str, str]] = []
    for path in sorted(tracked):
        kind = secret_file_kind(path.name)
        if kind is None or path.is_symlink() or not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                data = handle.read(_MAX_READ_BYTES)
        except OSError:
            _logger.debug("secret files: skipping unreadable %s", path)
            continue
        rel = path.relative_to(base).as_posix()
        if all(rel != seen for seen, _, _ in out):  # both unicode spellings may exist
            out.append((rel, kind, data.decode("utf-8", errors="replace")))
    return out
