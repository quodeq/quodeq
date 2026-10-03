"""How a refresh of a project's working copy ended.

The wire value of ``POST /api/projects/<project>/refresh``'s ``outcome``
(success) and, upper-cased, its error ``code``; the UI mirror is
``ui/src/vocab/refreshOutcome.js``.
"""
from __future__ import annotations

from enum import StrEnum


class RefreshOutcome(StrEnum):
    """UPDATED and UP_TO_DATE are successes; every other member is a refusal."""

    UPDATED = "updated"
    UP_TO_DATE = "up_to_date"
    # The project has no git remote, or its folder is gone.
    NOT_REFRESHABLE = "not_refreshable"
    # An evaluation (or another refresh) is using the working copy.
    BUSY = "busy"
    DIRTY = "dirty"
    NO_UPSTREAM = "no_upstream"
    DIVERGED = "diverged"
    FETCH_FAILED = "fetch_failed"
