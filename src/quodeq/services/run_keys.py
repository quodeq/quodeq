"""Read a run's finding identity keys (for per-run cache-version scoping).

A run's score depends only on the suppressions whose keys are present in that
run, so the score cache versions each run by (dismissed ∩ these) + (deleted ∩
these). Keys come from ALL findings regardless of verdict, so a dismiss (which
only flips a verdict) never changes a run's key set. Best-effort: an
unreadable/absent db yields empty sets.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def read_run_key_sets(run_dir: Path) -> tuple[set[tuple], set[tuple]]:
    """Return ``(dismiss_keys, class_keys)`` present in *run_dir*'s findings.

    ``dismiss_keys``: ``{(requirement, file, line)}`` (matches ``dismissed_keys``).
    ``class_keys``: ``{(dimension, practice_id, file)}`` (matches ``deleted_keys``).
    """
    db_path = run_dir / "evaluation.db"
    if not db_path.is_file():
        return set(), set()
    dismiss: set[tuple] = set()
    cls: set[tuple] = set()
    try:
        from quodeq.data.sqlite.connection import open_evaluation_db  # noqa: PLC0415
        with open_evaluation_db(run_dir) as conn:
            for req, file, line, dim, pid in conn.execute(
                "SELECT requirement, file, line, dimension, practice_id FROM findings"
            ):
                dismiss.add((str(req or ""), str(file or ""), int(line or 0)))
                cls.add((str(dim or ""), str(pid or ""), str(file or "")))
    except sqlite3.DatabaseError:
        return set(), set()
    return dismiss, cls
