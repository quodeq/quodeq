"""File access over agent stream/JSONL output files.

The parsing itself is pure and lives in ``core/stream/events.py``; these
helpers add the file access, so both the analysis pipeline and the
services layer can reach them without a services -> analysis arrow.
The reads degrade to an empty result on unreadable files and the append
degrades to a logged warning: they feed progress counters and report
sidecars, never correctness.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from quodeq.core.stream.events import extract_files_from_event, parse_stream_event
from quodeq.shared.logging import log_debug
from quodeq.shared.utils import open_text

_logger = logging.getLogger(__name__)


def count_files_in_stream(stream_file: Path) -> set[str]:
    """Extract unique file paths from Read/Grep tool_use events in the stream."""
    files: set[str] = set()
    try:
        with open_text(stream_file) as f:
            for line in f:
                data = parse_stream_event(line)
                if data is not None:
                    files.update(extract_files_from_event(data))
    except (OSError, ValueError) as exc:
        log_debug(f"Failed to count files from stream {stream_file}: {exc}")
    return files


def count_active_agent_streams(
    evidence_dir: Path,
    dim_id: str,
    *,
    window_s: float,
    now: float | None = None,
) -> int:
    """Count ``<dim>_agent-*.stream`` files modified in the last *window_s* seconds.

    *now* overrides the wall clock for tests. 0 when the directory is
    absent or unreadable — this feeds an active-agents heuristic.
    """
    if not evidence_dir.is_dir():
        return 0
    cutoff = (now if now is not None else time.time()) - window_s
    count = 0
    try:
        for p in evidence_dir.glob(f"{dim_id}_agent-*.stream"):
            try:
                if p.stat().st_mtime >= cutoff:
                    count += 1
            except OSError:
                continue
    except OSError as exc:
        _logger.debug("stream directory glob failed: %s", exc)
    return count


def latest_dim_activity_mtime(evidence_dir: Path, dim_id: str) -> float | None:
    """Latest mtime among a dim's evidence jsonl and any surviving agent streams.

    None when neither exists (or neither is statable). Used as the "done" end-
    of-activity signal when a dimension's transition timestamps are unavailable
    (see ``services._scan_progress_elapsed.dim_elapsed_s``): agent streams are deleted
    at dimension completion, so they rarely survive, but the evidence file's
    own mtime remains as the fallback signal.
    """
    best: float | None = None
    for candidate in (
        evidence_dir / f"{dim_id}_evidence.jsonl",
        *evidence_dir.glob(f"{dim_id}_agent-*.stream"),
    ):
        try:
            mtime = candidate.stat().st_mtime
        except OSError:
            continue
        if best is None or mtime > best:
            best = mtime
    return best


def append_jsonl_rows(path: Path, rows: Iterable[dict]) -> None:
    """Append *rows* to *path* as JSONL lines.

    A failed append is logged as a warning and swallowed: the rows are
    already merged into the caller's in-memory state, so losing the file
    copy must never lose the run.
    """
    try:
        with path.open("a", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps(row) + "\n")
    except OSError:
        _logger.warning("could not append to %s", path, exc_info=True)


def append_jsonl_strict(path: Path, rows: Iterable[dict], *, append: bool = True) -> None:
    """Write *rows* as JSONL lines to *path*. Raises on any OSError.

    Unlike ``append_jsonl_rows``, a write failure here is never swallowed:
    the caller (cache replay) needs to know when a finding it believes is
    now on disk is not. ``append=False`` truncates and rewrites the file
    instead of appending to it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row) + "\n")


def iter_stream_lines(path: Path, *, missing_ok: bool = True) -> Iterator[str]:
    """Yield stripped, non-empty lines from *path*.

    ``missing_ok=True`` (the default): yields nothing when *path* does not
    exist. ``missing_ok=False``: a missing *path* raises ``FileNotFoundError``
    (an ``OSError``) when the file is opened instead -- for a caller that
    needs to tell "missing" apart from "empty" (e.g. to log a warning only
    once, from one ``except OSError``, instead of a separate existence
    pre-check that would race a concurrent delete). Any other read failure
    (permissions, a mid-read I/O error) always raises ``OSError``.
    """
    if missing_ok and not path.exists():
        return
    with open_text(path) as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if stripped:
                yield stripped


def count_jsonl_lines(jsonl_file: Path) -> int:
    """Count evidence lines in the JSONL file written by the MCP server."""
    try:
        if not jsonl_file.exists():
            return 0
        with open_text(jsonl_file) as f:
            return sum(1 for line in f if line.strip())
    except OSError as exc:
        log_debug(f"Failed to count JSONL lines from {jsonl_file}: {exc}")
        return 0
