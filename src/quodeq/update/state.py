"""Shared, on-disk update state at ~/.quodeq/update_state.json.

Read/written by three separate processes (dashboard, menubar, CLI), so it is
the single source of truth. Resolution mirrors shared/env.py: an explicit
QUODEQ_UPDATE_STATE_PATH wins, else <QUODEQ_DIR or ~/.quodeq>/update_state.json.
Basing the fallback on QUODEQ_DIR means the test suite's autouse
_isolate_quodeq_home fixture isolates this file automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from quodeq.shared.json_state import read_json_state, state_file_path, write_json_state

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
    return state_file_path("QUODEQ_UPDATE_STATE_PATH", _STATE_FILENAME, env)


def read_state(env: dict[str, str] | None = None) -> UpdateState:
    """Load the state, falling back to defaults on a missing or corrupt file.

    Unknown keys are dropped so an older process can read a file written by a
    newer one.
    """
    return read_json_state(Path(get_update_state_path(env)), UpdateState)


def write_state(state: UpdateState, env: dict[str, str] | None = None) -> None:
    """Persist the state atomically. Failures are logged, never raised."""
    write_json_state(state, Path(get_update_state_path(env)), "update", _logger)
