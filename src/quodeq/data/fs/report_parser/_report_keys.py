"""Finding identity keys of a run that has only its evaluation reports.

The mirror of ``findings_queries.read_run_key_sets`` for a run without an
``evaluation.db`` (legacy, JSON-only): the same keys, built from the parsed
reports instead of the ``findings`` table, so such a run scopes its cache
version and its suppression touch check like any other.

Memoized in-process against the reports' on-disk stamps, as the database
read is against the database's: a run in flight has no database yet and is
walked by every history read, and reparsing its reports per request would
cost more than the rest of the request.
"""
from __future__ import annotations

import os
from pathlib import Path

from quodeq.core.finding_identity import finding_dismiss_keys
from quodeq.data.fs.report_parser._evaluations import load_evaluations
from quodeq.data.mappers import parse_dimension_result
from quodeq.shared.stamp_memo import memoized_by_stamp


def read_report_key_sets(run_dir: Path) -> tuple[set[tuple], set[tuple]]:
    """``(dismiss_keys, class_keys)`` over every finding of the run's reports.

    Keys come from violations and compliance alike, as the database read
    takes them from all findings regardless of verdict. Empty when the run
    has no reports, and (best-effort, as the database read is on an
    unreadable db) when a report does not parse. Callers get fresh copies,
    so the memo can never be mutated through a result.
    """
    evaluation_dir = run_dir / "evaluation"
    stamp = _reports_stamp(evaluation_dir)
    if not stamp:
        return set(), set()
    keys = memoized_by_stamp(
        f"report-keys:{run_dir}", stamp, lambda: _read_report_key_sets(evaluation_dir))
    if keys is None:
        return set(), set()
    return set(keys[0]), set(keys[1])


def _reports_stamp(evaluation_dir: Path) -> tuple:
    """``(relative path, mtime, size)`` of every file under *evaluation_dir*; empty when none."""
    parts: list[tuple[str, int, int]] = []
    for root, dirs, files in os.walk(evaluation_dir):
        dirs.sort()
        for name in sorted(files):
            try:
                st = os.stat(os.path.join(root, name))
            except OSError:
                continue
            parts.append((os.path.relpath(os.path.join(root, name), evaluation_dir),
                          st.st_mtime_ns, st.st_size))
    return tuple(parts)


def _read_report_key_sets(evaluation_dir: Path) -> tuple[set[tuple], set[tuple]] | None:
    """Uncached read behind :func:`read_report_key_sets`; None when a report does not parse."""
    dismiss: set[tuple] = set()
    cls: set[tuple] = set()
    for raw in load_evaluations(evaluation_dir):
        try:
            dim = parse_dimension_result(raw)
        except (TypeError, ValueError):
            return None
        for f in (*dim.violations, *dim.compliance):
            dismiss |= finding_dismiss_keys(
                req=f.req, principle=f.practice_id, file=f.file, line=f.line, snippet=f.snippet)
            cls.add((dim.dimension or "", str(f.practice_id or ""), str(f.file or "")))
    return dismiss, cls
