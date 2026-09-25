"""Two project axes that both spell "local".

ProjectSource is where an assistant session's project data lives; the UI
mirror is ``ui/src/vocab/projectSource.js``. ProjectLocation is where a
registered project's code lives (``repository_info.json``'s ``location``).
"""
from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class ProjectSource(StrEnum):
    """Where project data comes from: the user's own evaluations or the read-only shared mirror.

    Also the project listing's/project card's ``source`` field, spelling
    where that project's evaluations were read from (see
    api/routes_shared_mirrors.py, api/routes_project_list.py).
    """

    LOCAL = "local"
    SHARED = "shared"


class ProjectLocation(StrEnum):
    """Where a registered project's code lives: a local checkout or an online repository URL."""

    LOCAL = "local"
    ONLINE = "online"


def session_source(session: Mapping[str, Any]) -> str:
    """Where *session*'s project data lives; a row with no ``source`` is local."""
    return session.get("source") or ProjectSource.LOCAL
