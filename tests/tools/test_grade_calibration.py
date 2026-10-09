from __future__ import annotations

import json
from pathlib import Path

import pytest
from _grade_calibration_load import load_reports
from _grade_calibration_metrics import yardsticks
from grade_calibration import main, score_report
from quodeq.core.scoring.params import DEFAULT_PARAMS


def _report(path: Path, dimension: str, score: str, violations, files=1000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "dimension": dimension, "overallScore": score, "overallGrade": "Poor", "sourceFileCount": files,
        "filesRead": files, "principles": [{"name": "P", "score": score, "grade": "Poor"}],
        "violations": violations, "compliance": [], "totals": {"violationCount": len(violations), "complianceCount": 0},
    }), encoding="utf-8")


def test_harness_scores_and_reports_without_paths(tmp_path: Path, capsys) -> None:
    bad = [{"principle": "P", "req": "S-INT-2", "severity": "minor", "file": f"f{i}.java"} for i in range(900)]
    _report(tmp_path / "BenchmarkJava" / "r1" / "evaluation" / "security.json", "security", "4.5/10", bad)
    (tmp_path / "BenchmarkJava" / "r1" / "status.json").write_text('{"ai_provider": "x", "ai_model": "m"}')
    _report(tmp_path / "clean" / "r1" / "evaluation" / "security.json", "security", "9.0/10", [{"principle": "P", "req": "S-INT-2", "severity": "minor", "file": "a.java"}])
    reports = load_reports([tmp_path])
    scores = [score_report(r, DEFAULT_PARAMS, {"S-INT-2": "critical"}) for r in reports]
    out = yardsticks(reports, scores)
    assert out["benchmark_range"][1] < 3.0
    assert set(out["grade_shares"]) == {"Exemplary", "Good", "Adequate", "Poor", "Critical"}
    assert str(tmp_path) not in json.dumps(out)


def _two_models(tmp_path: Path) -> None:
    """One project, two models a day apart, the second run carrying a fixable rule."""
    one = [{"principle": "P", "req": "S-INT-2", "severity": "major", "file": f"f{i}.java"} for i in range(40)]
    two = one + [{"principle": "P", "req": "S-INT-9", "severity": "minor", "file": "z.java"}]
    for run, model, date, found in (("aaaa1111", "m1", "2026-09-01", one), ("bbbb2222", "m2", "2026-09-02", two)):
        _report(tmp_path / "proj-with-a-long-name" / run / "evaluation" / "security.json", "security", "5.0/10", found)
        report = tmp_path / "proj-with-a-long-name" / run / "evaluation" / "security.json"
        data = json.loads(report.read_text())
        data["date"] = date
        report.write_text(json.dumps(data))
        (tmp_path / "proj-with-a-long-name" / run / "status.json").write_text(json.dumps({"ai_provider": "p", "ai_model": model}))


def test_pairs_temporal_and_motion(tmp_path: Path) -> None:
    _two_models(tmp_path)
    reports = load_reports([tmp_path])
    scores = [score_report(r, DEFAULT_PARAMS, {}) for r in reports]
    out = yardsticks(reports, scores, motion=("bbbb", ["S-INT-9", "S-INT-2"]))
    assert out["model_pairs"] == 1
    assert out["model_deviation"] == pytest.approx(abs(scores[0] - scores[1]), abs=1e-3)
    assert out["motion"][0]["after"] == 10.0
    assert out["temporal_pairs"] == 0


def test_cli_prints_table_labels_and_grid_without_paths(tmp_path: Path, capsys) -> None:
    _two_models(tmp_path)
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({"proj-with-a-long-name": "Poor"}))
    grid = tmp_path / "grid.json"
    grid.write_text(json.dumps([{"baseK": 0.2}, {"baseK": 0.05}]))
    code = main([str(tmp_path), "--classes", "none", "--labels", str(labels), "--grid", str(grid), "--motion", "bbbb:S-INT-9"])
    out = capsys.readouterr().out
    assert code == 0
    assert "proj-with-a-" in out and "proj-with-a-long" not in out
    assert out.count("grid ") == 2
    assert "motion" in out and "match" in out
    assert str(tmp_path) not in out
    assert chr(0x2014) not in out
