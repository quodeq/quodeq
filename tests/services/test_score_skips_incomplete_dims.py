"""Scoring path skips dims marked incomplete in dimensions.json."""
from __future__ import annotations
import json
from pathlib import Path

from quodeq.data.fs.dimensions_state_store import DimState, write_dim_state


def _seed_run(tmp_path: Path) -> tuple[Path, Path]:
    reports = tmp_path / "reports"
    run = reports / "proj" / "run-1"
    (run / "evidence").mkdir(parents=True)
    (run / "evaluation").mkdir(parents=True)
    return reports, run


def _write_evidence_with_marker(run: Path, dim: str, file: str = "a.py") -> None:
    p = run / "evidence" / f"{dim}_evidence.jsonl"
    lines = [
        {"file": file, "req": "R-1", "t": "violation", "line": 1,
         "severity": "minor", "w": "w", "reason": "r",
         "p": "Modularity", "d": "maintainability"},
        {"_marker": "file_done", "file": file, "status": "ok"},
    ]
    p.write_text("".join(json.dumps(line) + "\n" for line in lines))


def _write_queue(run: Path, dim: str) -> None:
    queue = run / "evidence" / f"{dim}_queue.json"
    queue.write_text(json.dumps({
        "version": 2, "pending": [], "taken": [{"files": ["a.py"], "agent": "a1", "ts": 0}],
    }))


def _write_scan_json(reports: Path, project: str) -> None:
    scan = reports / project / "scan.json"
    scan.parent.mkdir(parents=True, exist_ok=True)
    scan.write_text(json.dumps({"sourceFileCount": 1}))


def test_done_dim_scored_incomplete_skipped(tmp_path: Path):
    from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence

    reports, run = _seed_run(tmp_path)
    _write_scan_json(reports, "proj")
    _write_evidence_with_marker(run, "d1")
    _write_evidence_with_marker(run, "d2")
    _write_queue(run, "d1")
    _write_queue(run, "d2")

    write_dim_state(run, "d1", DimState.PENDING)
    write_dim_state(run, "d1", DimState.RUNNING)
    write_dim_state(run, "d1", DimState.DONE)
    write_dim_state(run, "d2", DimState.PENDING)
    write_dim_state(run, "d2", DimState.RUNNING)
    write_dim_state(run, "d2", DimState.INCOMPLETE, reason="cancelled_by_user")

    _score_completed_evidence(str(reports), {
        "outputProject": "proj", "outputRunId": "run-1",
    })

    assert (run / "evaluation" / "d1.json").exists()
    assert not (run / "evaluation" / "d2.json").exists()


def test_idempotent_does_not_rescore(tmp_path: Path):
    from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence

    reports, run = _seed_run(tmp_path)
    _write_scan_json(reports, "proj")
    _write_evidence_with_marker(run, "d1")
    _write_queue(run, "d1")
    write_dim_state(run, "d1", DimState.PENDING)
    write_dim_state(run, "d1", DimState.RUNNING)
    write_dim_state(run, "d1", DimState.DONE)

    _score_completed_evidence(str(reports), {
        "outputProject": "proj", "outputRunId": "run-1",
    })
    first_mtime = (run / "evaluation" / "d1.json").stat().st_mtime_ns

    _score_completed_evidence(str(reports), {
        "outputProject": "proj", "outputRunId": "run-1",
    })
    second_mtime = (run / "evaluation" / "d1.json").stat().st_mtime_ns
    assert first_mtime == second_mtime


def test_cancelled_run_scoring_quarantines_off_standard_findings(tmp_path: Path, monkeypatch):
    """Scoring after cancellation must resolve the dimension's standard like a
    completed run does, so off-standard findings stay quarantined instead of
    re-entering the grade as phantom principles.
    """
    from quodeq.services.score_run import score_completed_evidence as _score_completed_evidence
    from quodeq.data.fs.dimensions_state_store import DimState, write_dim_state

    monkeypatch.setenv("QUODEQ_EVALUATORS_DIR", str(tmp_path / "no-evals"))
    reports, run = _seed_run(tmp_path)
    _write_scan_json(reports, "proj")
    dim = "maintainability"
    p = run / "evidence" / f"{dim}_evidence.jsonl"
    lines = [
        {"file": "a.py", "req": "M-MOD-1", "t": "violation", "line": 1,
         "severity": "minor", "w": "w", "reason": "r",
         "p": "Modularity", "d": dim},
        {"file": "z.py", "req": "X-1", "t": "violation", "line": 3,
         "severity": "critical", "w": "w", "reason": "r",
         "p": "NotInStandard", "d": dim},
        {"_marker": "file_done", "file": "a.py", "status": "ok"},
    ]
    p.write_text("".join(json.dumps(line) + "\n" for line in lines))
    _write_queue(run, dim)
    write_dim_state(run, dim, DimState.PENDING)
    write_dim_state(run, dim, DimState.RUNNING)
    write_dim_state(run, dim, DimState.DONE)

    _score_completed_evidence(str(reports), {
        "outputProject": "proj", "outputRunId": "run-1",
    })

    report = json.loads((run / "evaluation" / f"{dim}.json").read_text())
    assert report["quarantinedCount"] == 1
    principles = {v.get("principle") for v in report["violations"]}
    assert "NotInStandard" not in principles
