"""Keep the publisher's machine paths out of what a shared publish writes.

A local project's ``repository_info.json`` records the folder it was evaluated
in, and each dimension report repeats it in its ``project`` field. On a shared
repo both would tell every reader the publisher's username and directory
layout, and the folder means nothing on their machine anyway: a pulled local
project with an empty ``path`` asks its reader to locate their own copy.

An online project's ``path`` is its repository URL, which is what a reader
needs to clone it, so it is kept.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

from quodeq.core.types.project_source import ProjectLocation
from quodeq.services.wiring import read_json_object, replace_json_file

_REPORT_PROJECT_FIELD = "project"


def _is_machine_path(value: object) -> bool:
    """True for an absolute filesystem path, POSIX or Windows, wherever this runs."""
    return isinstance(value, str) and (
        PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()
    )


def published_repository_info(info: dict) -> dict:
    """*info* as the shared repo gets it: a local project's ``path`` blanked.

    The key stays (an empty string) because import requires it to be a string.
    """
    if info.get("location") == ProjectLocation.ONLINE or not _is_machine_path(info.get("path")):
        return dict(info)
    return {**info, "path": ""}


def scrub_report_paths(reports: list[Path]) -> None:
    """Rewrite each report whose ``project`` is a machine path to name only the folder."""
    for report in reports:
        data = read_json_object(report)
        if data is None or not _is_machine_path(data.get(_REPORT_PROJECT_FIELD)):
            continue
        data[_REPORT_PROJECT_FIELD] = PureWindowsPath(data[_REPORT_PROJECT_FIELD]).name
        replace_json_file(report, data, indent=2)
