"""Regression test for issue #621: a downgraded index.db must not crash.

When a newer quodeq migrates ``~/.quodeq/index.db`` to a ``schema_version``
this (older) binary doesn't support, the first index access previously raised
an uncaught ``UnsupportedIndexSchemaError`` — crashing the dashboard's
evaluations list wherever the index was first opened.

The index is a derived projection of the on-disk run files, so it is now
discarded and rebuilt at the open boundary instead of being fatal.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from quodeq.services._evaluations_index import EvaluationsIndex
from quodeq.services._job_model import InMemoryJobStore
from quodeq.services.jobs import JobManager
from quodeq.shared.run_status import RunState, write_status


def _seed_run(reports_root: Path, project: str, run_id: str) -> None:
    """Create a finished run dir matching what a CLI/subprocess writes."""
    run_dir = reports_root / project / run_id
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    write_status(
        run_dir,
        state=RunState.DONE,
        job_id=f"ext-{run_id}",
        started_at="2026-05-22T19:00:00+00:00",
        dimensions=["security"],
    )


def _write_downgraded_index(db_path: Path) -> None:
    """Write an index.db whose schema_version is newer than this binary supports."""
    raw = sqlite3.connect(db_path)
    raw.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    raw.execute("INSERT INTO schema_version VALUES (99)")
    raw.commit()
    raw.close()


def test_list_rebuilds_downgraded_index_instead_of_crashing(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    _seed_run(reports_root, "proj-uuid", "run-uuid")

    index_db_path = tmp_path / "index.db"
    _write_downgraded_index(index_db_path)

    jobs = JobManager(job_store=InMemoryJobStore(), reports_root=reports_root)
    index = EvaluationsIndex(
        jobs=jobs,
        index_db_path=index_db_path,
        reports_root=reports_root,
    )

    # Previously raised UnsupportedIndexSchemaError on the first access; must now
    # degrade by discarding the stale DB and rebuilding from the run files.
    entries = index.list(reports_dir=reports_root)

    match = [e for e in entries if e.output_run_id == "run-uuid"]
    assert len(match) == 1, f"expected the run to survive the rebuild, got {match}"
    assert match[0].source == "external"
    assert match[0].status == "done"
