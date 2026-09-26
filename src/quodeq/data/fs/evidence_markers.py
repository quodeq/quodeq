"""Read ``file_done`` markers a dim's evidence JSONL accumulates during a run.

Dispatch workers append one ``file_done`` marker per file as they finish it;
cache replays write findings without markers, so counting these markers
measures fresh progress a run made itself, never carried-forward data (see
``quodeq.analysis._loop_guards``, the sole caller).
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.evidence.markers import JSONL_MARKER_FILE_DONE, FileDoneStatus


def tally_evidence_markers(jsonl_path: Path) -> tuple[int, int]:
    """Return ``(ok_count, error_count)`` from a dim's evidence JSONL.

    Counts each file once by its *latest* ``file_done`` marker status, matching
    the cache's ok_files semantics (a file that errored then re-succeeded counts
    as ok). Unreadable/missing files contribute nothing.
    """
    last_status: dict[str, str] = {}
    try:
        # errors="replace" so a corrupt (non-UTF8) evidence file degrades to
        # unparseable lines (dropped by the json.loads guard) instead of
        # raising UnicodeDecodeError out of an otherwise-successful run.
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if entry.get("_marker") != JSONL_MARKER_FILE_DONE:
                    continue
                file = entry.get("file")
                status = entry.get("status")
                if isinstance(file, str) and status in (
                    FileDoneStatus.OK, FileDoneStatus.ERROR,
                ):
                    last_status[file] = status
    except OSError:
        return 0, 0
    ok = sum(1 for s in last_status.values() if s == FileDoneStatus.OK)
    err = sum(1 for s in last_status.values() if s == FileDoneStatus.ERROR)
    return ok, err
