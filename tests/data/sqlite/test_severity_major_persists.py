"""Regression: 'major' severity findings must persist to evaluation.db.

The scoring engine, eval JSON files, and UI all use the severity bucket
'major' (between 'critical' and 'minor'). The evaluation.db schema's
CHECK constraint historically only allowed
``('critical','high','medium','low','minor')`` — 'major' was missing.

Combined with ``INSERT OR IGNORE`` in record_finding, every major-severity
event was silently dropped at insert time. The DB ended up with only
critical + minor rows, and recompute_grades scored against the partial
data. When a user dismissed all the criticals, the principle's score
jumped to 10.0 because the major-severity violations were never recorded
in the DB to begin with.

This test pins the contract: a Judgment with severity='major' must
land in the findings table.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import Judgment
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.state_store import SQLiteStateStore


def test_major_severity_finding_persists(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    store = SQLiteStateStore(run_dir)
    judgment = Judgment(
        practice_id="Integrity",
        verdict="violation",
        dimension="security",
        file="auth.py",
        line=10,
        reason="weak crypto hash",
        severity="major",
    )
    store.record_finding(judgment)

    with open_evaluation_db(run_dir) as conn:
        rows = conn.execute(
            "SELECT severity, file, line FROM findings WHERE practice_id='Integrity'",
        ).fetchall()

    assert rows == [("major", "auth.py", 10)], (
        f"'major' severity finding did not persist. The schema CHECK on the "
        f"severity column rejected it, and INSERT OR IGNORE swallowed the "
        f"error silently. DB rows for Integrity: {rows}. "
        f"This explains why dismissing critical findings on the UI made "
        f"principle scores jump to 10.0 — the majors were never in the DB."
    )


def test_all_canonical_severities_persist(tmp_path: Path) -> None:
    """Every severity the scoring engine and UI use must round-trip."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    store = SQLiteStateStore(run_dir)
    for i, sev in enumerate(["critical", "major", "minor"]):
        store.record_finding(Judgment(
            practice_id="P", verdict="violation", dimension="d",
            file=f"f{i}.py", line=i + 1, reason="r", severity=sev,
        ))

    with open_evaluation_db(run_dir) as conn:
        counts = dict(
            conn.execute(
                "SELECT severity, COUNT(*) FROM findings GROUP BY severity",
            ).fetchall(),
        )

    assert counts == {"critical": 1, "major": 1, "minor": 1}, (
        f"Not all canonical severities persisted: {counts}"
    )
