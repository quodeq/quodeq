"""Deployment enum and ProjectShape dataclass.

Split from ``project_shape.py`` to keep that file under the size ratchet's
300-line cap, and to break the import cycle between the facade and
``_project_shape_signals.py`` (both need ``Deployment``). ``Deployment`` and
``ProjectShape`` stay re-exported from ``project_shape.py``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Deployment(str, Enum):
    DESKTOP = "desktop"
    CLI = "cli"
    WEB_SERVICE = "web_service"
    LIBRARY = "library"
    MOBILE = "mobile"
    EMBEDDED = "embedded"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProjectShape:
    """Coarse classification of what a repository ships.

    Fields are populated best-effort from manifests; absent signals leave
    fields as their defaults (``UNKNOWN`` / empty list / ``None``). The
    finding pipeline reads ``deployment`` and ``is_single_user`` to decide
    whether hosted-service findings (concurrent callers, distributed state,
    blocking the request thread) deserve their default confidence.
    """

    deployment: Deployment = Deployment.UNKNOWN
    runtime_langs: list[str] = field(default_factory=list)
    web_frameworks: list[str] = field(default_factory=list)
    ui_lang: str | None = None
    is_single_user: bool = True

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["deployment"] = self.deployment.value
        return d
