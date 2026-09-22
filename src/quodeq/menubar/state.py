"""Shared, on-disk menu bar preference at ~/.quodeq/menubar_state.json.

Read/written by separate processes (dashboard runner, Flask API, the menu bar
app itself), so the file is the single source of truth. Resolution mirrors
update/state.py: an explicit QUODEQ_MENUBAR_STATE_PATH wins, else
<QUODEQ_DIR or ~/.quodeq>/menubar_state.json. Basing the fallback on
QUODEQ_DIR means the test suite's autouse _isolate_quodeq_home fixture
isolates this file automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from quodeq.shared.json_state import read_json_state, state_file_path, write_json_state

_logger = logging.getLogger(__name__)

_STATE_FILENAME = "menubar_state.json"


@dataclass
class MenubarState:
    """Whether the user wants the menu bar icon, as persisted on disk."""

    enabled: bool = False


def get_menubar_state_path(env: dict[str, str] | None = None) -> str:
    """Resolve the state file path. *env* overrides ``os.environ`` for tests."""
    return state_file_path("QUODEQ_MENUBAR_STATE_PATH", _STATE_FILENAME, env)


def read_state(env: dict[str, str] | None = None) -> MenubarState:
    """Load the preference, falling back to defaults on a missing or corrupt file.

    Unknown keys are dropped so an older process can read a file written by a
    newer one.
    """
    return read_json_state(Path(get_menubar_state_path(env)), MenubarState)


def write_state(state: MenubarState, env: dict[str, str] | None = None) -> None:
    """Persist the preference atomically. Failures are logged, never raised."""
    write_json_state(state, Path(get_menubar_state_path(env)), "menubar", _logger)


def set_enabled(enabled: bool, env: dict[str, str] | None = None) -> None:
    """Flip the icon preference, preserving any other fields in the file."""
    state = read_state(env)
    state.enabled = enabled
    write_state(state, env)


def is_enabled(env: dict[str, str] | None = None) -> bool:
    """True when the user has the menu bar icon turned on."""
    return read_state(env).enabled
