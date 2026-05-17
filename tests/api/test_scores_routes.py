"""Tests for /api/projects/<project>/scores/<run_id> (SQL-backed path).

Verifies that get_scores_raw reads from the SQL grade tables after projection,
and only falls back to the legacy in-memory rescore when grade tables are empty.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository
from quodeq.services.scoring import get_scores_raw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_run(
    reports_root: Path,
    project: str,
    run_id: str,
    violations: list[dict] | None = None,
    project_after: bool = True,
) -> Path:
    """Create run directory, write events.jsonl, optionally trigger projection."""
    run_dir = reports_root / project / "runs" / run_id
    run_dir.mkdir(parents=True)
    log = run_dir / "events.jsonl"
    writer = EventLogWriter(log)
    for v in (violations or []):
        writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(**v)))
    if project_after:
        project_dir = reports_root / project
        Projector().ensure_projected(log, run_dir, project_dir=project_dir)
    return run_dir


_DEFAULT_VIOLATION = dict(
    practice_id="P1", verdict="violation", dimension="Security",
    file="a.py", line=10, reason="weak hash", req="R1", severity="high",
)


# ---------------------------------------------------------------------------
# SQL path tests
# ---------------------------------------------------------------------------

def test_get_scores_raw_reads_from_sql_after_projection(tmp_path: Path) -> None:
    """After ensure_projected runs, get_scores_raw returns SQL-backed grades."""
    _seed_run(tmp_path, "myproject", "r1", violations=[_DEFAULT_VIOLATION])

    result = get_scores_raw(tmp_path, "myproject", "r1")

    assert "dimensions" in result
    assert "summary" in result
    security_dim = next(
        (d for d in result["dimensions"] if d["dimension"] == "Security"), None
    )
    assert security_dim is not None
    assert security_dim["overallScore"] is not None


def test_get_scores_raw_uses_sql_when_grades_present(tmp_path: Path, monkeypatch) -> None:
    """When grade tables have rows, get_scores_raw reads them, not the legacy rescore."""
    _seed_run(tmp_path, "myproject", "r1", violations=[_DEFAULT_VIOLATION])

    # Monkeypatch legacy rescore to raise so we prove it is NOT called.
    import quodeq.services.rescore as legacy_rescore_mod  # noqa: PLC0415
    def boom(*a, **kw):  # noqa: ANN001
        raise AssertionError("legacy rescore should not be called when SQL has grades")
    monkeypatch.setattr(legacy_rescore_mod, "rescore_dimensions", boom)

    result = get_scores_raw(tmp_path, "myproject", "r1")
    assert "dimensions" in result
    assert "summary" in result


def test_get_scores_raw_falls_back_to_legacy_when_grades_empty(tmp_path: Path) -> None:
    """If grade tables are empty (unprojected run), fallback to legacy path."""
    run_dir = tmp_path / "myproject" / "runs" / "r1"
    run_dir.mkdir(parents=True)
    log = run_dir / "events.jsonl"
    # Write a violation but do NOT project (so grade tables remain empty).
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        **_DEFAULT_VIOLATION,
    )))

    # The legacy path reads JSONL directly via get_run_dimensions; it should
    # not raise even without an evaluation.db.
    result = get_scores_raw(tmp_path, "myproject", "r1")
    assert "dimensions" in result or result == {"dimensions": [], "summary": {}}


def test_get_scores_raw_raises_file_not_found_for_missing_run(tmp_path: Path) -> None:
    """FileNotFoundError raised when run directory does not exist."""
    (tmp_path / "myproject" / "runs").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        get_scores_raw(tmp_path, "myproject", "nonexistent-run")


def test_get_scores_raw_includes_violations_list(tmp_path: Path) -> None:
    """Each dimension dict includes a violations list (used by the UI for filtering)."""
    _seed_run(tmp_path, "myproject", "r1", violations=[_DEFAULT_VIOLATION])

    result = get_scores_raw(tmp_path, "myproject", "r1")

    security_dim = next(
        (d for d in result["dimensions"] if d["dimension"] == "Security"), None
    )
    assert security_dim is not None
    assert "violations" in security_dim
    assert len(security_dim["violations"]) == 1


def test_get_scores_raw_includes_principles(tmp_path: Path) -> None:
    """Each dimension dict includes a principles list with per-principle grades."""
    _seed_run(tmp_path, "myproject", "r1", violations=[_DEFAULT_VIOLATION])

    result = get_scores_raw(tmp_path, "myproject", "r1")

    security_dim = next(
        (d for d in result["dimensions"] if d["dimension"] == "Security"), None
    )
    assert security_dim is not None
    assert "principles" in security_dim
    assert len(security_dim["principles"]) >= 1
    p = security_dim["principles"][0]
    assert "principle" in p
    assert "grade" in p


def test_get_scores_raw_includes_totals(tmp_path: Path) -> None:
    """Each dimension dict includes totals with violationCount and severity."""
    _seed_run(tmp_path, "myproject", "r1", violations=[_DEFAULT_VIOLATION])

    result = get_scores_raw(tmp_path, "myproject", "r1")

    security_dim = next(
        (d for d in result["dimensions"] if d["dimension"] == "Security"), None
    )
    assert security_dim is not None
    totals = security_dim.get("totals")
    assert totals is not None
    assert "violationCount" in totals
    assert totals["violationCount"] == 1
    assert "severity" in totals


def test_get_scores_raw_reflects_dismissal_via_sql(tmp_path: Path) -> None:
    """Dismissing a finding changes the next get_scores_raw call via SQL."""
    v1 = dict(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1", severity="high",
    )
    v2 = dict(
        practice_id="P1", verdict="violation", dimension="Security",
        file="b.py", line=20, reason="r", req="R2", severity="low",
    )
    _seed_run(tmp_path, "myproject", "r1", violations=[v1, v2])

    before = get_scores_raw(tmp_path, "myproject", "r1")
    before_dim = next(d for d in before["dimensions"] if d["dimension"] == "Security")
    before_count = before_dim["totals"]["violationCount"]

    # Dismiss one finding and re-project.
    from quodeq.services.dismissed import dismiss_finding  # noqa: PLC0415
    project_dir = tmp_path / "myproject"
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})
    run_dir = project_dir / "runs" / "r1"
    Projector().ensure_projected(run_dir / "events.jsonl", run_dir, project_dir=project_dir)

    after = get_scores_raw(tmp_path, "myproject", "r1")
    after_dim = next(d for d in after["dimensions"] if d["dimension"] == "Security")
    after_count = after_dim["totals"]["violationCount"]

    assert after_count == before_count - 1, (
        f"Expected violation count to drop by 1: before={before_count}, after={after_count}"
    )


def test_get_scores_raw_summary_has_required_fields(tmp_path: Path) -> None:
    """The summary dict contains dimensionsCount, overallGrade, numericAverage."""
    _seed_run(tmp_path, "myproject", "r1", violations=[_DEFAULT_VIOLATION])

    result = get_scores_raw(tmp_path, "myproject", "r1")

    summary = result.get("summary", {})
    assert "dimensionsCount" in summary
    assert summary["dimensionsCount"] == 1
    assert "overallGrade" in summary
