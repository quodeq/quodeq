"""Tests for /api/projects/<project>/scores/<run_id> (SQL-backed path).

Verifies that get_scores_raw reads from the SQL grade tables after projection,
and returns an empty shape when grade tables are empty (unprojected run).
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
    run_dir = reports_root / project / run_id
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


def _scorable_violations(n: int = 5, *, practice: str = "P1", dimension: str = "Security") -> list[dict]:
    """N distinct violations for the same principle — enough to clear the
    medium-confidence floor in ``classify_confidence_level`` so the
    projector scores the principle instead of returning Insufficient."""
    return [
        dict(
            practice_id=practice, verdict="violation", dimension=dimension,
            file=f"f{i}.py", line=10 + i, reason="r", req=f"R{i}",
            severity="high",
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# SQL path tests
# ---------------------------------------------------------------------------

def test_get_scores_raw_reads_from_sql_after_projection(tmp_path: Path) -> None:
    """After ensure_projected runs, get_scores_raw returns SQL-backed grades.

    Uses 5 violations so the principle clears the medium-confidence floor
    (the CLI engine and the projector both treat thinner evidence as
    Insufficient, in which case ``overallScore`` is intentionally absent
    from the serialised camelCase dict).
    """
    _seed_run(tmp_path, "myproject", "r1", violations=_scorable_violations())

    result = get_scores_raw(tmp_path, "myproject", "r1")

    assert "dimensions" in result
    assert "summary" in result
    security_dim = next(
        (d for d in result["dimensions"] if d["dimension"] == "Security"), None
    )
    assert security_dim is not None
    assert security_dim["overallScore"] is not None


def test_get_scores_raw_falls_back_when_db_schema_too_new(tmp_path: Path) -> None:
    """A run whose evaluation.db was written by a NEWER Quodeq (higher schema
    version) must not crash the score read on an older binary; get_scores_raw
    degrades to the JSON-eval-file path instead of raising SchemaVersionError."""
    import sqlite3  # noqa: PLC0415

    from quodeq.data.sqlite._schema import SCHEMA_VERSION  # noqa: PLC0415

    _seed_run(tmp_path, "myproject", "r1", violations=_scorable_violations())
    db = tmp_path / "myproject" / "r1" / "evaluation.db"
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    conn.commit()
    conn.close()

    result = get_scores_raw(tmp_path, "myproject", "r1")  # must not raise

    assert "dimensions" in result
    assert "summary" in result


def test_get_scores_raw_falls_back_when_db_is_corrupt(tmp_path: Path) -> None:
    """A corrupt or half-written evaluation.db raises a generic
    sqlite3.DatabaseError (e.g. 'file is not a database'), not the narrower
    SchemaVersionError. The score read must still degrade to the JSON-eval-file
    path instead of crashing. SchemaVersionError already subclasses
    DatabaseError, so widening the seam to DatabaseError covers both."""
    _seed_run(tmp_path, "myproject", "r1", violations=_scorable_violations())
    db = tmp_path / "myproject" / "r1" / "evaluation.db"
    db.write_bytes(b"this is not a sqlite database at all")

    result = get_scores_raw(tmp_path, "myproject", "r1")  # must not raise

    assert "dimensions" in result
    assert "summary" in result


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


def test_get_scores_raw_returns_empty_shape_when_no_findings(tmp_path: Path) -> None:
    """When a run has no findings, get_scores_raw returns an empty shape.

    The summary now carries the rescore-engine's zero-state structure
    (``dimensionsCount=0``, empty ``gradeBreakdown``) instead of ``{}``,
    matching what runs without ``events.jsonl`` (the legacy JSON-file
    fallback path) return. Same empty meaning, slightly richer shape.
    """
    run_dir = tmp_path / "myproject" / "r1"
    run_dir.mkdir(parents=True)
    # Create an empty events log (no findings emitted).
    (run_dir / "events.jsonl").touch()

    result = get_scores_raw(tmp_path, "myproject", "r1")
    assert result["dimensions"] == []
    assert result["summary"].get("dimensionsCount", 0) == 0
    assert result["summary"].get("gradeBreakdown", []) == []


def test_get_scores_raw_reads_eval_json_when_no_events_log(tmp_path: Path) -> None:
    """Old runs that pre-date the event-log scoring engine have only
    ``evaluation/<dim>.json`` files — no ``events.jsonl``. ``get_scores_raw``
    must fall back to the JSON-file path so the dismiss-returns-scores flow
    works for these runs too. Without this fallback, every run in the 100+
    older history of a long-lived project returned an empty payload, and
    dismissing a finding silently failed to update the visible score.
    """
    import json
    run_dir = tmp_path / "myproject" / "r1"
    (run_dir / "evaluation").mkdir(parents=True)
    # Synthesize a minimal eval JSON file (matches the schema the parser
    # expects). One Security violation under principle "Integrity".
    (run_dir / "evaluation" / "Security.json").write_text(json.dumps({
        "schema_version": 1,
        "dimension": "Security",
        "project": "myproject",
        "runId": "r1",
        "overallScore": "7.0/10",
        "overallGrade": "Good",
        "principles": [{
            "name": "Integrity", "score": "7.0/10", "grade": "Good",
            "violations": [], "compliance": [],
        }],
        "violations": [{
            "principle": "Integrity", "req": "R1",
            "file": "a.py", "line": 10, "severity": "major",
            "reason": "bad", "title": "Bad",
        }],
        "compliance": [],
    }))

    result = get_scores_raw(tmp_path, "myproject", "r1")

    assert len(result["dimensions"]) > 0, (
        f"Expected dimensions in payload from eval JSON fallback, got {result}"
    )
    security = next((d for d in result["dimensions"] if d["dimension"] == "Security"), None)
    assert security is not None, (
        f"Security dimension missing from fallback payload: {result['dimensions']}"
    )


def test_get_scores_raw_raises_file_not_found_for_missing_run(tmp_path: Path) -> None:
    """FileNotFoundError raised when run directory does not exist."""
    (tmp_path / "myproject").mkdir(parents=True)
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
    run_dir = project_dir / "r1"
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
