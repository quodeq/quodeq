"""Keep what a shared publish must not carry out of the published files.

Machine paths, always. A local project's ``repository_info.json`` records the
folder it was evaluated in, and each dimension report repeats it in its
``project`` field. On a shared repo both would tell every reader the
publisher's username and directory layout, and the folder means nothing on
their machine anyway: a pulled local project with an empty ``path`` asks its
reader to locate their own copy. An online project's ``path`` is its
repository URL, which is what a reader needs to clone it, so it is kept.

Code, unless the shared repository opts in. Every finding in the event log,
the evidence logs and the reports quotes the code it is about (``snippet``)
and the lines around it (``context``). Without the opt-in the context is
dropped and the snippet becomes a token carrying the finding's fingerprint
(``core.finding_identity.withheld_snippet``), so dismissals, run diffs and
grades on a clone still match the findings they name.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath

from quodeq.core.finding_identity import withheld_snippet
from quodeq.core.types.project_source import ProjectLocation
from quodeq.services.wiring import read_json_object, replace_json_file
from quodeq.services.wiring_sync import ARCHIVE_FILENAME, rewrite_archive_logs, write_replacing

_REPORT_PROJECT_FIELD = "project"
_SNIPPET_FIELD = "snippet"
_CONTEXT_FIELD = "context"
_REQ_FIELD = "req"
_LOG_SUFFIX = ".jsonl"
_REPORT_SUFFIX = ".json"
_REPORTS_DIRNAME = "evaluation"


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


def _withhold(node: object) -> bool:
    """Replace every finding's snippet under *node* with its token and drop its context, in place; True when any changed."""
    if isinstance(node, list):
        return any([_withhold(item) for item in node])
    if not isinstance(node, dict):
        return False
    changed = False
    if _SNIPPET_FIELD in node:
        had_context = node.pop(_CONTEXT_FIELD, None) is not None
        snippet = node[_SNIPPET_FIELD]
        replacement = withheld_snippet(node.get(_REQ_FIELD), snippet) if isinstance(snippet, str) else snippet
        node[_SNIPPET_FIELD] = replacement
        changed = had_context or replacement != snippet
    return any([_withhold(value) for value in node.values()]) or changed


def _withhold_log(data: bytes) -> bytes:
    """A JSON-lines log without code, *data* itself when it holds none.

    A line that is not JSON is dropped rather than published as it is.
    """
    records, changed = [], False
    for line in data.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            changed = changed or bool(line.strip())
            continue
        changed = _withhold(record) or changed
        records.append(json.dumps(record, separators=(",", ":")))
    if not changed:
        return data
    return "".join(f"{r}\n" for r in records).encode("utf-8")


def _withhold_member(name: str, data: bytes) -> bytes:
    return _withhold_log(data) if name.endswith(_LOG_SUFFIX) else data


def withhold_snippets(paths: Iterable[Path]) -> None:
    """Take the code out of each published run file in *paths*: logs, run archives and reports."""
    for path in paths:
        if path.name == ARCHIVE_FILENAME:
            rewrite_archive_logs(path, _withhold_member)
        elif path.suffix == _LOG_SUFFIX:
            original = path.read_bytes()
            data = _withhold_log(original)
            if data is not original:
                write_replacing(path, lambda tmp, d=data: tmp.write_bytes(d))
        elif path.suffix == _REPORT_SUFFIX and path.parent.name == _REPORTS_DIRNAME:
            report = read_json_object(path)
            if report is not None and _withhold(report):
                replace_json_file(path, report, indent=2)
