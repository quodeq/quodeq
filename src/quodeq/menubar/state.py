"""Shared, on-disk menu bar preference at ~/.quodeq/menubar_state.json.

Read/written by separate processes (dashboard runner, Flask API, the menu bar
app itself), so the file is the single source of truth. Resolution mirrors
update/state.py: an explicit QUODEQ_MENUBAR_STATE_PATH wins, else
<QUODEQ_DIR or ~/.quodeq>/menubar_state.json. Basing the fallback on
QUODEQ_DIR means the test suite's autouse _isolate_quodeq_home fixture
isolates this file automatically.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

_STATE_FILENAME = "menubar_state.json"


@dataclass
class MenubarState:
    enabled: bool = False


def get_menubar_state_path(env: dict[str, str] | None = None) -> str:
    environ = env if env is not None else os.environ
    explicit = environ.get("QUODEQ_MENUBAR_STATE_PATH")
    if explicit:
        return explicit
    base = environ.get("QUODEQ_DIR") or str(Path.home() / ".quodeq")
    return str(Path(base) / _STATE_FILENAME)


def read_state(env: dict[str, str] | None = None) -> MenubarState:
    path = Path(get_menubar_state_path(env))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return MenubarState()
    if not isinstance(raw, dict):
        return MenubarState()
    known = {f for f in MenubarState().__dict__}
    return MenubarState(**{k: v for k, v in raw.items() if k in known})


def write_state(state: MenubarState, env: dict[str, str] | None = None) -> None:
    path = Path(get_menubar_state_path(env))
    # Fresh unique temp file then os.replace() onto the target so concurrent
    # writers never share a temp path and a reader never sees a half-written
    # file (same pattern as update/state.py).
    tmp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(state), indent=2))
        os.replace(tmp_name, path)
    except OSError:
        # fail-silent: a preference write is never worth crashing over
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def set_enabled(enabled: bool, env: dict[str, str] | None = None) -> None:
    state = read_state(env)
    state.enabled = enabled
    write_state(state, env)


def is_enabled(env: dict[str, str] | None = None) -> bool:
    return read_state(env).enabled
