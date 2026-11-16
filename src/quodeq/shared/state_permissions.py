"""Owner-only access to Quodeq's state directory (POSIX).

The state directory holds evaluated code: evidence and event logs carry
snippets, reports quote them, and the SQLite databases (the run index, the
score cache, the assistant's history, each run's ``evaluation.db``) are built
from them. Created under the default umask it is world-readable, so any other
account on the machine could read every evaluated repository's findings.

:func:`secure_state_dir` runs at startup: it creates the root 0700, takes the
group and other bits off an existing root (that alone closes everything
beneath it), and makes the databases 0600 so a copy or a relocated
evaluations folder keeps them private. Only entries this account owns are
touched, and symlinks are never followed. Windows has no mode bits to fix:
the profile directory's ACL already keeps other users out.
"""
from __future__ import annotations

import logging
import os
import stat
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

from quodeq.shared.constants import PLATFORM_WIN32
from quodeq.shared.env_paths import get_evaluations_dir, get_quodeq_dir

_logger = logging.getLogger(__name__)

_DIR_MODE = 0o700
_OWNER_ONLY = 0o700  # the bits kept on an existing entry: group and other are dropped
_DB_GLOB = "*.db*"  # a database and its -wal / -shm sidecars
# Where databases live: the state root (index, score cache, assistant), each
# project folder, and each run folder.
_ROOT_DB_GLOBS = (_DB_GLOB,)
_EVALUATIONS_DB_GLOBS = (f"*/{_DB_GLOB}", f"*/*/{_DB_GLOB}")


def _restrict(path: Path) -> bool:
    """Drop group and other access from *path* when this account owns it; True when changed."""
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or st.st_uid != os.getuid():
        return False
    mode = stat.S_IMODE(st.st_mode)
    if not mode & ~_OWNER_ONLY:
        return False
    os.chmod(path, mode & _OWNER_ONLY)
    return True


def _databases(root: Path, evaluations: Path) -> Iterator[Path]:
    for pattern in _ROOT_DB_GLOBS:
        yield from root.glob(pattern)
    for pattern in _EVALUATIONS_DB_GLOBS:
        yield from evaluations.glob(pattern)


def secure_state_dir(env: Mapping[str, str] | None = None) -> int:
    """Make the state root owner-only and its databases 0600; the number of entries changed.

    Best-effort: a file that vanishes or cannot be changed is skipped, never raised.
    """
    if sys.platform == PLATFORM_WIN32:
        return 0
    environ = dict(env) if env is not None else None
    root = get_quodeq_dir(environ)
    changed = 0
    try:
        root.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
        changed += _restrict(root)
    except OSError as exc:
        _logger.warning("could not make %s private: %s", root, exc)
        return changed
    for db in _databases(root, Path(get_evaluations_dir(env=environ))):
        try:
            changed += _restrict(db)
        except OSError as exc:  # removed or replaced meanwhile
            _logger.debug("could not make %s private: %s", db, exc)
    if changed:
        _logger.info("made %d Quodeq state entries owner-only under %s", changed, root)
    return changed
