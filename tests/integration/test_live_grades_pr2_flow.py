"""End-to-end: scan → grades populated → dismiss → next read reflects updated grade."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.services.dismissed import dismiss_finding


def test_full_grade_flow(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "runs" / "r1"
    run_dir.mkdir(parents=True)

    # Two findings in Security (varied severity), one in Reliability.
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1", severity="critical",
    )))
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P2", verdict="violation", dimension="Security",
        file="b.py", line=20, reason="r", req="R2", severity="medium",
    )))
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P3", verdict="violation", dimension="Reliability",
        file="c.py", line=30, reason="r", req="R3", severity="low",
    )))

    # Trigger projection + grade compute via a read.
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")

    store = SQLiteStateStore(run_dir)
    dim_rows = {r["dimension"]: r for r in store.read_dimension_scores()}
    assert "Security" in dim_rows
    assert "Reliability" in dim_rows
    sec_before = dim_rows["Security"]["score"]
    assert sec_before is not None

    # Dismiss the critical Security finding.
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    # Re-read triggers ensure_projected → grade recompute.
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")

    sec_after = store.read_dimension_scores()
    sec_after_row = next(r for r in sec_after if r["dimension"] == "Security")
    sec_after_score = sec_after_row["score"]

    # Security grade improves because the worst-severity violation is gone.
    assert sec_after_score > sec_before, (
        f"Expected Security score to improve after dismissing critical finding; "
        f"before={sec_before}, after={sec_after_score}"
    )

    # Reliability dimension is unaffected.
    rel_after = next(r for r in sec_after if r["dimension"] == "Reliability")
    assert rel_after["score"] == dim_rows["Reliability"]["score"]
