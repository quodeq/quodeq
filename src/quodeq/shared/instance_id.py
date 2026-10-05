"""The identity of one quodeq state folder.

A random id written once into ``QUODEQ_DIR/instance-id`` and reported by
``/api/health``. The UI keys per-install choices on it (the welcome's "skip
for now"): a wiped or renamed state folder gets a new id, so those choices
start over with it, even though the desktop webview's own storage lives
elsewhere on disk (macOS keeps it under ~/Library/WebKit, not in the folder).
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from quodeq.shared.env_paths import get_quodeq_dir

INSTANCE_ID_FILE = "instance-id"
_logger = logging.getLogger(__name__)


def read_instance_id(env: dict[str, str] | None = None) -> str:
    """The state folder's id, created on first read.

    An unreadable or unwritable folder yields a fresh id for this process
    only: the health route must answer either way.
    """
    path: Path = get_quodeq_dir(env) / INSTANCE_ID_FILE
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except OSError as exc:
        _logger.debug("no instance id at %s yet (%s); minting one", path, exc)
    fresh = uuid.uuid4().hex
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fresh + "\n", encoding="utf-8")
    except OSError as exc:
        _logger.warning("could not persist the instance id at %s: %s", path, exc)
    return fresh
