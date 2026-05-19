"""Regression: dismiss flow works with the production directory layout.

Production stores runs at ``<eval_dir>/<project>/<run_id>/`` (no ``runs/``
subdir). An earlier refactor mistakenly assumed ``<project>/runs/<run_id>/``
which silently broke dismiss + live-grade updates in production while
unit tests (which used the ``runs/`` layout) still passed.

These tests pin the real layout end-to-end so the divergence cannot recur.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.api._run_event_stream import WatcherState, compute_tick
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.services.dismissed import dismiss_finding, dismissed_keys, load_dismissed


def _seed_finding(run_dir: Path, *, req: str, file: str, line: int, dimension: str = "Security") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension=dimension,
        file=file, line=line, reason="r", req=req, severity="high",
    )))
    # Project events into evaluation.db so the finding exists in SQL.
    SqliteFindingsRepository(run_dir).list_by_dimension(dimension)


def test_dismiss_sticks_in_sql_under_prod_layout(tmp_path: Path) -> None:
    """Production layout: dismiss must flip findings.verdict to 'dismissed'."""
    eval_dir = tmp_path / "evaluations"
    project_dir = eval_dir / "proj1"
    run_dir = project_dir / "run1"  # NO `runs/` segment
    _seed_finding(run_dir, req="R1", file="a.py", line=10)

    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    # Re-listing must trigger projection of actions.jsonl.
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")

    keys = dismissed_keys(project_dir)
    assert keys == {("R1", "a.py", 10)}, (
        f"Dismissal did not project to SQL under prod layout. "
        f"actions.jsonl exists at {project_dir / 'actions.jsonl'}, "
        f"but dismissed_keys returned {keys}"
    )


def test_load_dismissed_returns_entries_under_prod_layout(tmp_path: Path) -> None:
    """Production layout: load_dismissed must surface dismissed entries."""
    eval_dir = tmp_path / "evaluations"
    project_dir = eval_dir / "proj1"
    run_dir = project_dir / "run1"
    _seed_finding(run_dir, req="R1", file="a.py", line=10)

    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")

    items = load_dismissed(project_dir)
    assert len(items) == 1
    assert items[0]["req"] == "R1"
    assert items[0]["file"] == "a.py"
    assert items[0]["line"] == 10


def test_dismiss_under_prod_layout_recomputes_scores(tmp_path: Path) -> None:
    """Production layout: dismiss + projection must drop the finding from the
    score path. (The score now arrives via the dismiss HTTP response instead
    of an SSE event — see tests/api/test_routes_findings.py for that contract.)
    """
    eval_dir = tmp_path / "evaluations"
    project_dir = eval_dir / "proj1"
    run_dir = project_dir / "run1"
    _seed_finding(run_dir, req="R1", file="a.py", line=10)

    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")

    from quodeq.services.scoring import get_scores_raw  # noqa: PLC0415
    payload = get_scores_raw(eval_dir, "proj1", "run1")
    security = next((d for d in payload.get("dimensions", []) if d.get("dimension") == "Security"), None)
    assert security is None or security.get("overallScore") is None, (
        "After dismissing the only finding, the Security dimension should "
        f"have no score in the rescored payload. Got: {security}"
    )
