"""Two project axes that both spell "local".

ProjectSource is where an assistant session's project data lives; the UI
mirror is ``ui/src/vocab/projectSource.js``. ProjectLocation is where a
registered project's code lives (``repository_info.json``'s ``location``).
"""
from __future__ import annotations

from enum import StrEnum


class ProjectSource(StrEnum):
    """An assistant session's data source: the user's own evaluations or the read-only shared mirror."""

    LOCAL = "local"
    SHARED = "shared"


class ProjectLocation(StrEnum):
    """Where a registered project's code lives: a local checkout or an online repository URL."""

    LOCAL = "local"
    ONLINE = "online"
