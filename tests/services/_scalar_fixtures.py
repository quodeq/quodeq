"""Shared fixtures for scalar-fast-path tests: runs with baked SQL grades.

Mirrors tests/services/test_scoring_sql_overlay.py::_build_event_log_run.
"""
import json
from pathlib import Path

from quodeq.data.sqlite.state_store import SQLiteStateStore


def build_projected_run(
    reports: Path, project: str, run_id: str,
    dims: dict[str, tuple[float, str]],
    totals_by_dim: dict[str, dict] | None = None,
) -> Path:
    """A projected run with real (non-NULL) SQL grades baked directly.

    *dims*: ``{dimension: (score_float, grade_str)}``.
    *totals_by_dim*: optional eval-JSON ``"totals"`` per dimension so full reads
    carry non-zero severity.

    Scores are written straight into ``dimension_scores`` via
    ``record_dimension_score`` (NOT via ``recompute_grades``, which hits the
    confidence gate and yields NULL scores for low-evidence findings). The empty
    event log is frozen as fully projected so ``ensure_projected()`` is a no-op
    and won't wipe them.
    """
    run_dir = reports / project / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text("")
    store = SQLiteStateStore(run_dir)
    store.save_projected_size((run_dir / "events.jsonl").stat().st_size)
    for dim, (score, grade) in dims.items():
        store.record_dimension_score(dimension=dim, score=score, grade=grade)

    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    for dim, (score, grade) in dims.items():
        (eval_dir / f"{dim}.json").write_text(json.dumps({
            "schema_version": 1, "dimension": dim, "discipline": "Python",
            "date": "2026-05-23", "sourceFileCount": 100,
            "overallScore": f"{score}/10", "overallGrade": grade,
            "principles": [], "violations": [], "compliance": [],
            "totals": (totals_by_dim or {}).get(
                dim, {"violationCount": 0, "complianceCount": 0, "severity": {}}),
        }), encoding="utf-8")

    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "manifest.json").write_text(
        json.dumps({"language_stats": {}}), encoding="utf-8")
    return run_dir


def build_legacy_run(
    reports: Path, project: str, run_id: str, dims: dict[str, tuple[str, str]],
) -> Path:
    """A legacy run: eval JSON only, no events.jsonl, no evaluation.db.

    *dims*: ``{dimension: (overallScore, overallGrade)}``.
    """
    run_dir = reports / project / run_id
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    for dim, (score, grade) in dims.items():
        (eval_dir / f"{dim}.json").write_text(json.dumps({
            "dimension": dim, "overallScore": score, "overallGrade": grade,
            "principles": [], "violations": [], "compliance": [],
            "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
        }))
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "manifest.json").write_text(json.dumps({"language_stats": {}}))
    return run_dir
