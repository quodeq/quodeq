from __future__ import annotations

import json
import statistics
from datetime import date, timedelta
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
    assert out["motion"][0]["after"] is None  # no findings left: production gives the principle no row
    only_extra = yardsticks(reports, scores, motion=("bbbb", ["S-INT-9"]))
    assert only_extra["motion"][0]["after"] == scores[0]  # same findings as the first run
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


def _run(root: Path, project: str, run: str, dimension: str, model: str, day: int, hits: int) -> None:
    """A run on day *day* of the fixture calendar whose dimension report has *hits* majors in 1000 files."""
    found = [{"principle": "P", "req": "S-INT-2", "severity": "major", "file": f"f{i}.java"} for i in range(hits)]
    path = root / project / run / "evaluation" / f"{dimension}.json"
    _report(path, dimension, "5.0/10", found)
    data = json.loads(path.read_text())
    data["date"] = (date(2026, 8, 1) + timedelta(days=day - 1)).isoformat()
    path.write_text(json.dumps(data))
    (root / project / run / "status.json").write_text(json.dumps({"ai_provider": "p", "ai_model": model}))


def test_pairing_temporal_shares_and_signal_to_noise(tmp_path: Path) -> None:
    # security: m1 on day 1 and 10, m2 on day 12 and 70. The latest m2 run is 60 days from m1's latest: no pair.
    _run(tmp_path, "proj", "s1", "security", "m1", 1, 5)
    _run(tmp_path, "proj", "s2", "security", "m1", 10, 40)
    _run(tmp_path, "proj", "s3", "security", "m2", 12, 20)
    _run(tmp_path, "proj", "s4", "security", "m2", 70, 80)
    # reliability: m1 day 10 against m2 day 12, two days apart: the one pair.
    _run(tmp_path, "proj", "r1", "reliability", "m1", 10, 10)
    _run(tmp_path, "proj", "r2", "reliability", "m2", 12, 30)
    reports = load_reports([tmp_path])
    scores = [score_report(r, DEFAULT_PARAMS, {}) for r in reports]
    by_run = {r.run: s for r, s in zip(reports, scores)}
    out = yardsticks(reports, scores)

    assert out["model_pairs"] == 1
    assert out["model_deviation"] == pytest.approx(abs(by_run["r1"] - by_run["r2"]), abs=1e-3)
    # consecutive same-model runs: m1 day 1 to 10 and m2 day 12 to 70 (reliability has one run per model)
    deltas = [abs(by_run["s2"] - by_run["s1"]), abs(by_run["s4"] - by_run["s3"])]
    assert out["temporal_pairs"] == 2
    assert min(deltas) > 0
    assert out["temporal_mean_delta"] == pytest.approx(statistics.mean(deltas), abs=1e-3)
    assert sum(out["grade_shares"].values()) == pytest.approx(100, abs=0.5)
    between = statistics.pstdev([by_run["s4"], by_run["r2"]])  # latest run per project and dimension
    assert out["signal_to_noise"] == pytest.approx(between / abs(by_run["r1"] - by_run["r2"]), abs=0.01)


def test_names_are_cut_and_paths_never_printed(tmp_path: Path, capsys) -> None:
    secret = "/Users/secret/work/AnotherVeryLongProjectName"
    long_name = "a-very-long-indexed-project-name"
    _run(tmp_path, "uuid-1", "run1", "security", "m1", 1, 20)
    _run(tmp_path, "uuid-2", "run1", "security", "m1", 1, 20)
    first = tmp_path / "uuid-1" / "run1" / "evaluation" / "security.json"
    second = tmp_path / "uuid-2" / "run1" / "evaluation" / "security.json"
    for path in (first, second):
        data = json.loads(path.read_text())
        data["project"] = secret
        path.write_text(json.dumps(data))
    (tmp_path / "project_index.json").write_text(json.dumps({f"{long_name}\x00{secret}": "uuid-1"}))
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps({long_name: "Good", "AnotherVeryLongProjectName": "Good"}))
    assert main([str(tmp_path), "--classes", "none", "--labels", str(labels), "--motion", "run1:S-INT-2"]) == 0
    out = capsys.readouterr().out
    assert long_name[:12] in out and "AnotherVeryL" in out
    for forbidden in (long_name, "AnotherVeryLongProjectName", "/Users/secret", str(tmp_path)):
        assert forbidden not in out


def test_a_principle_stored_as_insufficient_is_still_scored(tmp_path: Path) -> None:
    """Thin principles an older formula gated are scored by the current one, so the harness keeps them."""
    found = [{"principle": "P", "req": "S-INT-2", "severity": "minor", "file": "a.java"}]
    path = tmp_path / "proj" / "r1" / "evaluation" / "security.json"
    _report(path, "security", "9.0/10", found)
    data = json.loads(path.read_text())
    data["principles"] = [{"name": "P", "score": None, "grade": "Insufficient"}, {"name": "Empty", "grade": "Insufficient"}]
    path.write_text(json.dumps(data))
    (report,) = load_reports([tmp_path])
    assert set(report.principles) == {"P"}
