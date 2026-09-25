"""One shared ``~/.quodeq/<name>.json`` state file, read and written safely.

Two subsystems keep a small dataclass on disk that several processes read
and write: the menu bar preference (``menubar.state``) and the update state
(``update.state``). Path resolution, the tolerant read and the atomic write
are the same for both and live here, so the two cannot drift.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, TypeVar

from quodeq.shared.env_paths import home_state_dir
from quodeq.shared.env_resolve import resolve_env

_StateT = TypeVar("_StateT")


def state_file_path(
    explicit_var: str, filename: str, env: dict[str, str] | None = None,
) -> str:
    """Where the state file lives: *explicit_var* wins, else ``<QUODEQ_DIR or ~/.quodeq>/filename``.

    Basing the fallback on ``QUODEQ_DIR`` means the test suite's autouse
    ``_isolate_quodeq_home`` fixture isolates the file automatically. *env*
    overrides ``os.environ`` for tests.
    """
    environ = resolve_env(env)
    explicit = environ.get(explicit_var)
    if explicit:
        return explicit
    base = environ.get("QUODEQ_DIR") or str(home_state_dir())
    return str(Path(base) / filename)


def read_json_state(path: Path, cls: type[_StateT]) -> _StateT:
    """Load *path* into a *cls* instance, falling back to defaults.

    A missing, unreadable, non-JSON or non-object file yields ``cls()``.
    Unknown keys are dropped so an older process can read a file written by
    a newer one.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cls()
    if not isinstance(raw, dict):
        return cls()
    known = {f for f in cls().__dict__}
    return cls(**{k: v for k, v in raw.items() if k in known})


def dump_json_and_replace(
    fd: int, tmp_path: str, path: Path, data: object, *, indent: int | None = None,
) -> None:
    """Write *data* as JSON into the open temp file *fd*, then move *tmp_path* onto *path*.

    The publish step of an atomic JSON write: the caller makes the temp file
    (``tempfile.mkstemp`` next to *path*) and owns cleanup and error policy.
    ``os.replace`` is atomic and overwrites on every platform, so a reader
    never sees a half-written file. *fd* is closed on return or on error.
    """
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent)
    os.replace(tmp_path, str(path))


def write_json_state(
    state: Any, path: Path, label: str, logger: logging.Logger,
) -> None:
    """Persist dataclass *state* to *path* atomically; failures are logged, never raised.

    A fresh unique temp file plus ``os.replace()`` onto the target, so
    concurrent writers never share a temp path and a reader never sees a
    half-written file. *label* names the state in the debug lines.
    """
    tmp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        dump_json_and_replace(tmp_fd, tmp_name, path, asdict(state), indent=2)
    except OSError as exc:
        # fail-silent: this write is never worth crashing over
        logger.debug("%s state write failed (fail-soft): %s", label, exc)
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError as inner_exc:
                logger.debug("temp %s state file %s not removed: %s", label, tmp_name, inner_exc)
