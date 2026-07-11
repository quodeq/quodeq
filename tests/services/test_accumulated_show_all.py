"""The accumulated view keeps every dimension's last valid run, however old.

Regression for the removed "current standard" scoping: dimensions whose last
valid run predated the last-5-runs config window used to be dropped from the
accumulated payload — hiding them from the overview cards, headline grade,
project card, violations page, and map. They must survive and count toward
the average; retirement is explicit via the dismiss/delete actions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from quodeq.services.accumulated import _build_accumulated_for_runs
from quodeq.services.ports import RunInfo


def _write_eval(run_dir: Path, name: str, score: str, grade: str) -> None:
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "dimension": name, "overallScore": score, "overallGrade": grade,
        "principles": [], "violations": [], "compliance": [],
    }
    (eval_dir / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    ev = run_dir / "evidence"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / f"{name}_evidence.json").write_text(
        json.dumps({"dimension": name, "discipline": "typescript"}), encoding="utf-8",
    )


def _setup_run(run_dir: Path, dims: list[tuple[str, str, str]], configured: list[str]) -> None:
    for name, score, grade in dims:
        _write_eval(run_dir, name, score, grade)
    (run_dir / "evidence").mkdir(parents=True, exist_ok=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}", encoding="utf-8")
    (run_dir / "scan.json").write_text("{}", encoding="utf-8")
    (run_dir / "dimensions.json").write_text(
        json.dumps({
            "schema_version": 1,
            "dimensions": {d: {"state": "done"} for d in configured},
        }),
        encoding="utf-8",
    )


def test_dimension_older_than_five_runs_survives_and_counts(tmp_path: Path) -> None:
    """C's only valid run is older than the last 5 runs' configs. It must
    still appear with its last score and move the average."""
    project = "proj"
    reports_root = tmp_path / "evaluations"
    run_infos = []
    # 5 recent eligible runs configure and evaluate only {A, B}.
    for i in range(5):
        rd = reports_root / project / f"run-{i}"
        _setup_run(rd, [("A", "8.0", "A"), ("B", "6.0", "C")], configured=["A", "B"])
        run_infos.append(RunInfo(
            run_id=f"run-{i}", date_iso=f"2026-07-{20 - i:02d}",
            date_label="d", status="complete",
        ))
    # Older 6th run carries C's only valid score.
    old = reports_root / project / "run-old"
    _setup_run(old, [("C", "9.0", "A")], configured=["A", "B", "C"])
    run_infos.append(RunInfo(
        run_id="run-old", date_iso="2026-07-01", date_label="d", status="complete",
    ))

    result = _build_accumulated_for_runs(reports_root, project, run_infos, None)

    dims = sorted(d.dimension for d in result.all_dimensions)
    assert dims == ["A", "B", "C"], f"old dim C must survive, got {dims}"
    c = next(d for d in result.all_dimensions if d.dimension == "C")
    assert c.from_run_id == "run-old"
    # Unknown dimension names all weigh 1.0, so the average is
    # (8.0 + 6.0 + 9.0) / 3 = 7.7 — C counts toward the headline grade.
    assert result.avg_score == pytest.approx(7.7)
