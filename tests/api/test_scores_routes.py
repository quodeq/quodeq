"""Tests for /api/projects/<project>/scores/<run_id> (SQL-backed path).

Verifies the route's error contract and that get_scores_raw reads from the
SQL grade tables after projection, degrading to the JSON eval files when the
database is unreadable. Payload-shape and slim-variant tests live in
test_scores_routes_payload.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.services.scoring import get_scores_raw
from tests.api._scores_routes_helpers import _DEFAULT_VIOLATION, _scorable_violations, _seed_run


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "reports"))
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


def test_project_run_scores_wraps_unexpected_error(client, monkeypatch):
    monkeypatch.setattr(
        "quodeq.api._scores_routes.get_scores_slim",
        lambda *a, **kw: (_ for _ in ()).throw(ValueError("corrupt scores.json")),
    )
    resp = client.get("/api/projects/demo/scores/run123")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["code"] == "SCORES_READ_FAILED"


def test_project_run_scores_propagates_an_error_outside_the_narrowed_tuple(client, monkeypatch):
    """A RuntimeError (not OSError/sqlite3.Error/ValueError) is a real bug in
    get_scores_slim, not a read failure, so the route's own narrow tuple
    does not catch it, and it is not wrapped into a SCORES_READ_FAILED 500.
    It still escapes the route -- the app-wide fallback handler
    (api/_error_handlers.py) is what turns it into a generic coded 500
    instead of Flask's default HTML page."""
    monkeypatch.setattr(
        "quodeq.api._scores_routes.get_scores_slim",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("unexpected bug")),
    )
    resp = client.get("/api/projects/demo/scores/run123")

    assert resp.status_code == 500
    body = resp.get_json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "unexpected bug" not in resp.get_data(as_text=True)


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


def test_get_scores_raw_surfaces_provenance_downgrade(tmp_path: Path) -> None:
    """Issue #656: a finding the provenance gate downgraded must keep its
    provenance_downgrade flag through the SQL-backed scores read path
    (build_response_from_grade_tables / _SELECT_ACTIVE), so the dashboard
    badge can render. A dropped column here silently regresses it to False."""
    violations = _scorable_violations()  # 5 distinct Security violations
    violations[0] = {
        **violations[0], "file": "downgraded.py",
        "severity": "major", "provenance_downgrade": True,
    }
    _seed_run(tmp_path, "myproject", "r1", violations=violations)

    result = get_scores_raw(tmp_path, "myproject", "r1")

    security = next(d for d in result["dimensions"] if d["dimension"] == "Security")
    target = next(v for v in security["violations"] if v["file"] == "downgraded.py")
    assert target["provenanceDowngrade"] is True
    # Parity: an un-downgraded finding stays False (no over-marking).
    other = next(v for v in security["violations"] if v["file"] != "downgraded.py")
    assert other["provenanceDowngrade"] is False


def test_get_scores_raw_surfaces_scope_downgrade(tmp_path: Path) -> None:
    """A finding the scope gate capped from major to minor must keep its
    scope_downgrade marker -- including WHICH rule fired -- through the
    SQL-backed scores read path (build_response_from_grade_tables /
    _SELECT_ACTIVE), so the dashboard can show what was waived and why.
    A dropped column here silently makes a waived finding indistinguishable
    from an ordinary minor."""
    violations = _scorable_violations()  # 5 distinct Security violations
    violations[0] = {
        **violations[0], "file": "downgraded.py",
        "severity": "minor",
        "scope_downgrade": {"rule": "sourceless_path", "from": "major", "to": "minor"},
    }
    _seed_run(tmp_path, "myproject", "r1", violations=violations)

    result = get_scores_raw(tmp_path, "myproject", "r1")

    security = next(d for d in result["dimensions"] if d["dimension"] == "Security")
    target = next(v for v in security["violations"] if v["file"] == "downgraded.py")
    assert target["scopeDowngrade"] == {"rule": "sourceless_path", "from": "major", "to": "minor"}
    # Parity: an un-downgraded finding has no marker at all (omitted, since
    # to_camel_dict drops None fields -- absence, not a bare False, is the
    # honest "not gated" signal for a dict-shaped marker).
    other = next(v for v in security["violations"] if v["file"] != "downgraded.py")
    assert "scopeDowngrade" not in other


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
