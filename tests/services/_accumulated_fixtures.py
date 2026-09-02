"""Shared fixtures for tests/services/test_accumulated_*.py siblings.

Split out of test_accumulated.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quodeq.core.types import DimensionResult
from quodeq.data.mappers import parse_dimension_result


def _dim(name: str, score: str = "7.5", grade: str = "B", **extra: Any) -> DimensionResult:
    """Build a minimal DimensionResult."""
    raw: dict[str, Any] = {"dimension": name, "overallScore": score, "overallGrade": grade, **extra}
    return parse_dimension_result(raw)


def _write_eval(path: Path, dim_name: str, score: str = "7.5", grade: str = "B", **extra: Any) -> None:
    """Write a minimal evaluation JSON file for a dimension."""
    path.mkdir(parents=True, exist_ok=True)
    data = {"dimension": dim_name, "overallScore": score, "overallGrade": grade, "principles": [], "violations": [], "compliance": [], **extra}
    (path / f"{dim_name}.json").write_text(json.dumps(data))


def _write_evidence(path: Path, dim_name: str, discipline: str = "typescript") -> None:
    """Write a minimal evidence JSON file."""
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{dim_name}_evidence.json").write_text(json.dumps({"dimension": dim_name, "discipline": discipline}))


def _setup_project(tmp_path: Path, project: str, runs: list[tuple[str, list[DimensionResult]]]) -> Path:
    """Set up a project directory with the given runs and dimensions.

    *runs* is a list of (run_id, [DimensionResult, ...]) pairs, newest first.
    Returns the reports root path.
    """
    reports_root = tmp_path / "evaluations"
    for run_id, dims in runs:
        run_dir = reports_root / project / run_id
        for dim in dims:
            dim_name = dim.dimension
            eval_dir = run_dir / "evaluation"
            _write_eval(eval_dir, dim_name, dim.overall_score or "7.5", dim.overall_grade or "B")
            evidence_dir = run_dir / "evidence"
            _write_evidence(evidence_dir, dim_name)
        evidence_dir = run_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "manifest.json").write_text("{}")
        (run_dir / "scan.json").write_text("{}")
    return reports_root
