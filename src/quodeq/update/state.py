"""Shared, on-disk update state at ~/.quodeq/update_state.json.

Read/written by three separate processes (dashboard, menubar, CLI), so it is
the single source of truth. Resolution mirrors shared/_env.py: an explicit
QUODEQ_UPDATE_STATE_PATH wins, else <QUODEQ_DIR or ~/.quodeq>/update_state.json.
Basing the fallback on QUODEQ_DIR means the test suite's autouse
_isolate_quodeq_home fixture isolates this file automatically.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from quodeq.shared.env_resolve import resolve_env

_logger = logging.getLogger(__name__)

_STATE_FILENAME = "update_state.json"


@dataclass
class UpdateState:
    """Everything the update subsystem remembers between runs.

    Written by whichever process last ran a check; the ETag is what keeps the
    GitHub releases call cheap.
    """

    auto_check_enabled: bool = True
    last_check_ts: str | None = None
    latest_version: str | None = None
    latest_url: str | None = None
    download_url: str | None = None
    is_security: bool = False
    etag: str | None = None
    dismissed_version: str | None = None
    disclosed: bool = False


def get_update_state_path(env: dict[str, str] | None = None) -> str:
    """Resolve the state file path. *env* overrides ``os.environ`` for tests."""
    environ = resolve_env(env)
    explicit = environ.get("QUODEQ_UPDATE_STATE_PATH")
    if explicit:
        return explicit
    base = environ.get("QUODEQ_DIR") or str(Path.home() / ".quodeq")
    return str(Path(base) / _STATE_FILENAME)


def read_state(env: dict[str, str] | None = None) -> UpdateState:
    """Load the state, falling back to defaults on a missing or corrupt file.

    Unknown keys are dropped so an older process can read a file written by a
    newer one.
    """
    path = Path(get_update_state_path(env))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UpdateState()
    if not isinstance(raw, dict):
        return UpdateState()
    known = {f for f in UpdateState().__dict__}
    return UpdateState(**{k: v for k, v in raw.items() if k in known})


def write_state(state: UpdateState, env: dict[str, str] | None = None) -> None:
    """Persist the state atomically. Failures are logged, never raised."""
    path = Path(get_update_state_path(env))
    # Write a fresh unique temp file then os.replace() onto the target so
    # concurrent writers (dashboard, menubar, CLI) never share a temp path
    # and a reader never sees a half-written file.
    tmp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(state), indent=2))
        os.replace(tmp_name, path)
    except OSError as exc:
        _logger.debug("update state write failed (fail-soft): %s", exc)
        # fail-silent: a notice is never worth crashing over
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError as inner_exc:
                _logger.debug("temp notice file %s not removed: %s", tmp_name, inner_exc)
