from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import Judgment
from quodeq.data.projection.grade_projector import recompute_grades
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.shared.dimensions_state import DimState, write_dim_state


def _seed(store: SQLiteStateStore, *, req: str, principle: str, dimension: str, severity: str = "medium") -> None:
    store.record_finding(Judgment(
        practice_id=principle, verdict="violation", dimension=dimension,
        file=f"{req}.py", line=1, reason="r", req=req, severity=severity,
    ))


def test_recompute_grades_writes_dimension_and_principle_rows(tmp_path: Path) -> None:
    """Seed 5+ findings per principle so they clear the confidence floor —
    otherwise the projector now correctly returns Insufficient (no
    numeric score) for thin evidence, matching the CLI engine.
    """
    store = SQLiteStateStore(tmp_path)
    for i in range(5):
        _seed(store, req=f"P1-{i}", principle="P1", dimension="Security", severity="high")
    for i in range(5):
        _seed(store, req=f"P2-{i}", principle="P2", dimension="Security", severity="medium")

    recompute_grades(tmp_path)

    dim_rows = store.read_dimension_scores()
    assert len(dim_rows) == 1
    assert dim_rows[0]["dimension"] == "Security"
    assert dim_rows[0]["score"] is not None

    p_rows = store.read_principle_grades()
    assert len(p_rows) == 2
    assert {r["principle_id"] for r in p_rows} == {"P1", "P2"}


def test_recompute_grades_below_confidence_floor_writes_insufficient(
    tmp_path: Path,
) -> None:
    """A principle with one finding clears the empty-tally guard but trips
    the confidence-level check, so the projector now returns
    ``Insufficient`` instead of a real score — matching the CLI engine.
    """
    store = SQLiteStateStore(tmp_path)
    _seed(store, req="R1", principle="P1", dimension="Security", severity="high")

    recompute_grades(tmp_path)

    p_rows = store.read_principle_grades()
    assert len(p_rows) == 1
    assert p_rows[0]["principle_id"] == "P1"
    assert p_rows[0]["grade"] == "Insufficient"
    assert p_rows[0]["score"] is None


def test_recompute_grades_excludes_dismissed(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    _seed(store, req="R1", principle="P1", dimension="Security", severity="high")
    _seed(store, req="R2", principle="P1", dimension="Security", severity="critical")
    store.update_verdict(req="R2", file="R2.py", line=1, verdict="dismissed")

    recompute_grades(tmp_path)

    p_rows = store.read_principle_grades()
    assert p_rows[0]["finding_count"] == 1  # only R1 counts
    assert p_rows[0]["dismissed_count"] == 1


def test_recompute_grades_clears_stale_rows(tmp_path: Path) -> None:
    """When all findings for a dimension are dismissed, the dimension row vanishes."""
    store = SQLiteStateStore(tmp_path)
    _seed(store, req="R1", principle="P1", dimension="Security")
    recompute_grades(tmp_path)
    assert len(store.read_dimension_scores()) == 1

    store.update_verdict(req="R1", file="R1.py", line=1, verdict="dismissed")
    recompute_grades(tmp_path)

    assert store.read_dimension_scores() == []
    assert store.read_principle_grades() == []


def test_recompute_grades_handles_multiple_dimensions(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    _seed(store, req="R1", principle="P1", dimension="Security")
    _seed(store, req="R2", principle="P2", dimension="Reliability")

    recompute_grades(tmp_path)

    dim_rows = store.read_dimension_scores()
    assert {r["dimension"] for r in dim_rows} == {"Security", "Reliability"}


def test_recompute_grades_principle_with_only_dismissed_still_appears(tmp_path: Path) -> None:
    """If a principle has findings, all dismissed, it should NOT appear in principle_grades
    (the principle is effectively gone from the dimension). This guards the empty-input
    contract: compute_principle_grade should never receive findings=[] AND compliance=[]
    because we only enumerate principles that have at least one non-dismissed finding."""
    store = SQLiteStateStore(tmp_path)
    _seed(store, req="R1", principle="P1", dimension="Security")
    _seed(store, req="R2", principle="P2", dimension="Security")
    # Dismiss everything for P1.
    store.update_verdict(req="R1", file="R1.py", line=1, verdict="dismissed")

    recompute_grades(tmp_path)

    p_rows = store.read_principle_grades()
    # Only P2 should appear — P1 has no non-dismissed findings.
    assert {r["principle_id"] for r in p_rows} == {"P2"}


def test_recompute_grades_no_findings_clears_tables(tmp_path: Path) -> None:
    """Idempotent on empty input — no exception, both tables empty."""
    store = SQLiteStateStore(tmp_path)
    recompute_grades(tmp_path)
    assert store.read_dimension_scores() == []
    assert store.read_principle_grades() == []


def test_recompute_grades_carries_exit_reason_from_dim_state(tmp_path: Path) -> None:
    """A dimension marked DONE with exit_reason=failure_streak in dimensions.json
    carries that reason onto its dimension_scores row (so the grade layer can
    flag/exclude it)."""
    store = SQLiteStateStore(tmp_path)
    for i in range(5):
        _seed(store, req=f"P1-{i}", principle="P1", dimension="flexibility", severity="high")
    write_dim_state(tmp_path, "flexibility", DimState.RUNNING)
    write_dim_state(tmp_path, "flexibility", DimState.DONE, exit_reason="failure_streak")

    recompute_grades(tmp_path)

    rows = store.read_dimension_scores()
    flex = next(r for r in rows if r["dimension"] == "flexibility")
    assert flex["score"] is not None
    assert flex["exit_reason"] == "failure_streak"


def test_recompute_grades_exit_reason_none_when_done_clean(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    for i in range(5):
        _seed(store, req=f"P1-{i}", principle="P1", dimension="security", severity="high")
    write_dim_state(tmp_path, "security", DimState.RUNNING)
    write_dim_state(tmp_path, "security", DimState.DONE)

    recompute_grades(tmp_path)

    rows = store.read_dimension_scores()
    sec = next(r for r in rows if r["dimension"] == "security")
    assert sec["exit_reason"] is None
