from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    name: str
    parent: str | None = None
    display_name: str | None = None
    discipline: str | None = None
    path: str | None = None
    location: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectEntry:
    id: str
    name: str
    parent: str | None = None
    display_name: str | None = None
    discipline: str | None = None
    path: str | None = None
    location: str | None = None
    runs_count: int = 0
    latest_run_id: str | None = None
    latest_date: str | None = None
    path_exists: bool | None = None
    files_count: int | None = None
    latest_grade: str | None = None
    latest_score: float | None = None
    language_stats: dict[str, int] = field(default_factory=dict)
    scan_date: str | None = None
    total_files: int | None = None
    analyzed_files: int | None = None
