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
import tempfile
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
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return UpdateState()
    if not isinstance(raw, dict):
        return UpdateState()
    known = {f for f in UpdateState().__dict__}
    return UpdateState(**{k: v for k, v in raw.items() if k in known})


def write_state(state: UpdateState, env: dict[str, str] | None = None) -> None:
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
    except OSError:
        # fail-silent: a notice is never worth crashing over
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
