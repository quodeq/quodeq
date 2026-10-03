"""Shared, on-disk update state at ~/.quodeq/update_state.json.

Read/written by three separate processes (dashboard, menubar, CLI), so it is
the single source of truth. QUODEQ_UPDATE_STATE_PATH overrides the location;
otherwise it sits in QUODEQ_DIR (default ~/.quodeq).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quodeq.shared.json_state import JsonStateFile

_logger = logging.getLogger(__name__)


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


_STATE_FILE = JsonStateFile(
    UpdateState, "QUODEQ_UPDATE_STATE_PATH", "update_state.json", "update", _logger,
)


def get_update_state_path(env: dict[str, str] | None = None) -> str:
    """Where the update state file lives (*env* stands in for ``os.environ``)."""
    return _STATE_FILE.path(env)


def read_state(env: dict[str, str] | None = None) -> UpdateState:
    """The last check's results and the user's update choices; defaults if the file is unusable."""
    return _STATE_FILE.read(get_update_state_path(env))


def write_state(state: UpdateState, env: dict[str, str] | None = None) -> None:
    """Persist the state atomically. Failures are logged, never raised."""
    _STATE_FILE.write(state, get_update_state_path(env))
