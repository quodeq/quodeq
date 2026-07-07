"""The accumulated view is scoped to the latest run's configured dimensions.

A project that stopped evaluating a dimension (e.g. clean-architecture)
still carries it in old runs / evaluation.db drift. The accumulated grade
must reflect the CURRENT standard — the dimensions the latest eligible run
actually configured — and drop the stale ones.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.core.types import DimensionResult
from quodeq.core.types.mappers import parse_dimension_result
from quodeq.services.accumulated import (
    _build_accumulated_for_runs,
    _scope_to_configured,
)
from quodeq.services.ports import RunInfo


def _dim(name: str, score: str = "7.5", grade: str = "B") -> DimensionResult:
    return parse_dimension_result({"dimension": name, "overallScore": score, "overallGrade": grade})


# ---------------------------------------------------------------------------
# _scope_to_configured (pure helper)
# ---------------------------------------------------------------------------

class TestScopeToConfigured:
    def test_drops_dims_not_configured(self):
        dims = [_dim("A"), _dim("B"), _dim("C")]
        result = _scope_to_configured(dims, {"A", "B"})
        assert sorted(d.dimension for d in result) == ["A", "B"]

    def test_empty_configured_fails_open(self):
        # Unknown config (empty set) -> never drop everything.
        dims = [_dim("A"), _dim("B")]
        result = _scope_to_configured(dims, set())
        assert sorted(d.dimension for d in result) == ["A", "B"]

    def test_keeps_all_when_all_configured(self):
        dims = [_dim("A"), _dim("B")]
        result = _scope_to_configured(dims, {"A", "B", "C"})
        assert sorted(d.dimension for d in result) == ["A", "B"]


# ---------------------------------------------------------------------------
# _build_accumulated_for_runs — end-to-end scoping through the real reader
# ---------------------------------------------------------------------------

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


def test_accumulated_subset_rerun_does_not_collapse(tmp_path: Path) -> None:
    """The latest eligible run is a targeted subset re-run configuring only {A}.
    The full standard {A,B,C} must survive because prior eligible runs configured
    it — the accumulated grade must NOT collapse to a single dimension."""
    project = "proj"
    reports_root = tmp_path / "evaluations"
    # Newest run: subset re-run, only A.
    subset = reports_root / project / "run-subset"
    _setup_run(subset, [("A", "8.0", "A")], configured=["A"])
    # Prior eligible runs configured the full {A,B,C}, with findings for each.
    prior = reports_root / project / "run-full"
    _setup_run(prior, [("A", "8.0", "A"), ("B", "6.0", "C"), ("C", "7.0", "B")],
               configured=["A", "B", "C"])

    run_infos = [
        RunInfo(run_id="run-subset", date_iso="2026-07-05", date_label="d", status="complete"),
        RunInfo(run_id="run-full", date_iso="2026-07-01", date_label="d", status="complete"),
    ]
    result = _build_accumulated_for_runs(reports_root, project, run_infos, None)
    dims = sorted(d.dimension for d in result.all_dimensions)
    assert dims == ["A", "B", "C"], f"subset re-run must not collapse standard, got {dims}"


def test_accumulated_fails_open_without_config(tmp_path: Path) -> None:
    """No dimensions.json / status.json on the latest run -> do not filter."""
    project = "proj"
    reports_root = tmp_path / "evaluations"
    latest = reports_root / project / "run-new"
    # Set up run but then remove the config signal.
    _setup_run(latest, [("A", "8.0", "A"), ("C", "9.0", "A")], configured=["A"])
    (latest / "dimensions.json").unlink()

    run_infos = [
        RunInfo(run_id="run-new", date_iso="2026-07-05", date_label="Jul 5", status="complete"),
    ]
    result = _build_accumulated_for_runs(reports_root, project, run_infos, None)
    dims = sorted(d.dimension for d in result.all_dimensions)
    # Fail-open: both dims survive because config is unreadable.
    assert dims == ["A", "C"], f"fail-open should keep all dims, got {dims}"
