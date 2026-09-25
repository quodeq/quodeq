"""Shared, on-disk menu bar preference at ~/.quodeq/menubar_state.json.

Read/written by separate processes (dashboard runner, Flask API, the menu bar
app itself), so the file is the single source of truth. Set
QUODEQ_MENUBAR_STATE_PATH to put it elsewhere (see
``shared.json_state.state_file_path``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quodeq.shared.json_state import JsonStateFile

_logger = logging.getLogger(__name__)


@dataclass
class MenubarState:
    """Whether the user wants the menu bar icon, as persisted on disk."""

    enabled: bool = False


_STATE_FILE = JsonStateFile(
    MenubarState, "QUODEQ_MENUBAR_STATE_PATH", "menubar_state.json", "menubar", _logger,
)


def get_menubar_state_path(env: dict[str, str] | None = None) -> str:
    """Resolve the state file path. *env* overrides ``os.environ`` for tests."""
    return _STATE_FILE.path(env)


def read_state(env: dict[str, str] | None = None) -> MenubarState:
    """Load the preference, falling back to defaults on a missing or corrupt file.

    Unknown keys are dropped so an older process can read a file written by a
    newer one.
    """
    return _STATE_FILE.read(get_menubar_state_path(env))


def write_state(state: MenubarState, env: dict[str, str] | None = None) -> None:
    """Persist the preference atomically. Failures are logged, never raised."""
    _STATE_FILE.write(state, get_menubar_state_path(env))


def set_enabled(enabled: bool, env: dict[str, str] | None = None) -> None:
    """Flip the icon preference, preserving any other fields in the file."""
    state = read_state(env)
    state.enabled = enabled
    write_state(state, env)


def is_enabled(env: dict[str, str] | None = None) -> bool:
    """True when the user has the menu bar icon turned on."""
    return read_state(env).enabled
