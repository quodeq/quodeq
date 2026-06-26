"""Shared, on-disk update state at ~/.quodeq/update_state.json.

Read/written by three separate processes (dashboard, menubar, CLI), so it is
the single source of truth. Resolution mirrors shared/_env.py: an explicit
QUODEQ_UPDATE_STATE_PATH wins, else <QUODEQ_DIR or ~/.quodeq>/update_state.json.
Basing the fallback on QUODEQ_DIR means the test suite's autouse
_isolate_quodeq_home fixture isolates this file automatically.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

_STATE_FILENAME = "update_state.json"


@dataclass
class UpdateState:
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
    environ = env if env is not None else os.environ
    explicit = environ.get("QUODEQ_UPDATE_STATE_PATH")
    if explicit:
        return explicit
    base = environ.get("QUODEQ_DIR") or str(Path.home() / ".quodeq")
    return str(Path(base) / _STATE_FILENAME)


def read_state(env: dict[str, str] | None = None) -> UpdateState:
    path = Path(get_update_state_path(env))
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return UpdateState()
    if not isinstance(raw, dict):
        return UpdateState()
    known = {f for f in UpdateState().__dict__}
    return UpdateState(**{k: v for k, v in raw.items() if k in known})


def write_state(state: UpdateState, env: dict[str, str] | None = None) -> None:
    path = Path(get_update_state_path(env))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2))
        os.replace(tmp, path)
    except OSError:
        pass  # fail-silent: a notice is never worth crashing over
