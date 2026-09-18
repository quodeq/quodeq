"""Shared run builders, score helpers and the cache-clearing fixture for tests/services/test_scoring_parity*.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.core.events.models import Judgment
from quodeq.data.projection.grade_projector import recompute_grades
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.dismissed import dismiss_finding


def _dismiss_and_freeze_sql(project_dir: Path, run_dir: Path, finding: dict) -> None:
    """Dismiss a finding project-wide, then freeze the SQL projection stale.

    On real data, a run's baked SQL ``dimension_scores`` do NOT reflect
    project-wide dismissals that accrued after the scan: the actions-log size
    is already checkpointed, so re-projection is a no-op and the SQL grade
    stays RAW. We reproduce that here by advancing the run's
    ``actions_projected_size`` checkpoint to the current actions.jsonl size, so
    ``ensure_projected`` skips re-applying the dismissal to SQL. This is what
    forces ``get_scores_raw``'s SQL fast path to serve the raw score unless it
    routes through the project-wide rescore -- the exact real-world failure.
    """
    dismiss_finding(project_dir, finding)
    actions_log = project_dir / "actions.jsonl"
    size = actions_log.stat().st_size if actions_log.is_file() else 0
    SQLiteStateStore(run_dir).save_actions_projected_size(size)

_DIM = "performance"
_RUN = "20260101T000000"


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def _build_run_with_violations(reports_root: Path, project: str) -> Path:
    """One complete event-log run whose eval JSON carries real violations.

    Findings are baked into SQL (so read_dimension_scores / the SQL fast path
    have real grades) AND written into the eval JSON's ``violations`` array (so
    read_run_data -> _rescore_dimension sees them and a project-wide dismiss can
    move the score). This is what makes the raw vs dismiss-adjusted score differ.
    """
    run_dir = reports_root / project / _RUN
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text("")

    store = SQLiteStateStore(run_dir)
    violations = [
        Judgment(
            practice_id="p1", dimension=_DIM, req="R1", verdict="violation",
            severity="critical", file="a.py", line=1, title="crit", reason="null deref",
        ),
        *[
            Judgment(
                practice_id="p1", dimension=_DIM, req=f"R{i}", verdict="violation",
                severity="major", file=f"f{i}.py", line=10, title=f"t{i}", reason=f"r{i}",
            )
            for i in range(2, 6)
        ],
    ]
    compliance = [
        Judgment(
            practice_id="p1", dimension=_DIM, req=f"C{i}", verdict="compliance",
            severity="minor", file=f"c{i}.py", line=20, title=f"ct{i}", reason=f"cr{i}",
        )
        for i in range(6)
    ]
    for f in [*violations, *compliance]:
        store.record_finding(f)
    store.save_projected_size((run_dir / "events.jsonl").stat().st_size)
    recompute_grades(run_dir, params=DEFAULT_PARAMS)

    row = {r["dimension"]: r for r in store.read_dimension_scores()}[_DIM]
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{_DIM}.json").write_text(json.dumps({
        "schema_version": 1, "dimension": _DIM, "project": project,
        "discipline": "Python", "date": "2026-05-23", "sourceFileCount": 100,
        "overallScore": f"{row['score']}/10", "overallGrade": row["grade"],
        "principles": [{"name": "p1", "score": f"{row['score']}/10", "grade": row["grade"]}],
        "violations": [
            {
                # The parser maps ``practice_id`` from the ``principle`` key, so
                # carry both — deletions key on (dimension, principle, file).
                "practiceId": v.practice_id, "principle": v.practice_id,
                "req": v.req, "file": v.file, "line": v.line,
                "severity": v.severity, "title": v.title, "reason": v.reason,
            }
            for v in violations
        ],
        "compliance": [
            {
                "practiceId": c.practice_id, "req": c.req, "file": c.file, "line": c.line,
                "severity": c.severity, "title": c.title, "reason": c.reason,
            }
            for c in compliance
        ],
        "totals": {
            "violationCount": len(violations), "complianceCount": len(compliance),
            "severity": {"critical": 1, "major": 4, "minor": 0},
        },
    }), encoding="utf-8")

    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "manifest.json").write_text(
        json.dumps({"language_stats": {}}), encoding="utf-8")
    return run_dir


def _perf_score(dims) -> str | None:
    for d in dims:
        name = d.get("dimension") if isinstance(d, dict) else getattr(d, "dimension", None)
        if name == _DIM:
            return d.get("overallScore") if isinstance(d, dict) else getattr(d, "overall_score", None)
    return None


def _num(score: str | None) -> float | None:
    if not score or "/" not in str(score):
        return None
    return float(str(score).split("/")[0])
