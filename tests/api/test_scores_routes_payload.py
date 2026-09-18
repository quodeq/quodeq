"""get_scores_raw payload shape, JSON-eval fallback, dismissal and the slim variant."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.data.projection.projector import Projector
from quodeq.services.scoring import get_scores_raw, get_scores_slim
from tests.api._scores_routes_helpers import _DEFAULT_VIOLATION, _scorable_violations, _seed_run


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


# ---------------------------------------------------------------------------
# Slim variant (GET /scores/<runId> payload diet)
# ---------------------------------------------------------------------------

def test_get_scores_slim_reduces_violations_to_identity_keys(tmp_path: Path) -> None:
    """The run-scores route serves ``get_scores_slim``: each violation keeps
    only the ``req``/``file``/``line`` fields the Explorer's rescore merge
    uses as identity keys — heavy fields (reason, snippet, context) are gone.
    """
    _seed_run(tmp_path, "myproject", "r1", violations=_scorable_violations())

    result = get_scores_slim(tmp_path, "myproject", "r1")

    dim = next(d for d in result["dimensions"] if d["dimension"] == "Security")
    assert dim["violations"], "slim payload must still carry violation keys"
    for v in dim["violations"]:
        assert set(v.keys()) == {"req", "file", "line"}
        assert v["file"] and v["line"] is not None


def test_get_scores_slim_drops_compliance_but_keeps_scores(tmp_path: Path) -> None:
    """Compliance bodies are never read from this payload — the list is
    emptied while grades, principles, totals, and summary stay identical to
    the raw payload.
    """
    _seed_run(tmp_path, "myproject", "r1", violations=_scorable_violations())

    raw = get_scores_raw(tmp_path, "myproject", "r1")
    slim = get_scores_slim(tmp_path, "myproject", "r1")

    assert slim["summary"] == raw["summary"]
    for raw_dim, slim_dim in zip(raw["dimensions"], slim["dimensions"]):
        assert slim_dim["compliance"] == []
        assert slim_dim["dimension"] == raw_dim["dimension"]
        assert slim_dim["overallScore"] == raw_dim["overallScore"]
        assert slim_dim["overallGrade"] == raw_dim["overallGrade"]
        assert slim_dim["principles"] == raw_dim["principles"]
        assert slim_dim["totals"] == raw_dim["totals"]
        assert len(slim_dim["violations"]) == len(raw_dim["violations"])
