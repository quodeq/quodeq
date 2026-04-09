"""Tests for parent-project aggregation in accumulated view."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.core.types import DimensionResult
from quodeq.core.types.mappers import parse_dimension_result
from quodeq.services.accumulated import (
    _find_children,
    _compute_parent_accumulated,
    compute_accumulated,
)


# ---------------------------------------------------------------------------
# Helpers (reused patterns from test_accumulated.py)
# ---------------------------------------------------------------------------

def _dim(name: str, score: str = "7.5", grade: str = "B") -> DimensionResult:
    return parse_dimension_result({"dimension": name, "overallScore": score, "overallGrade": grade})


def _write_eval(path: Path, dim_name: str, score: str = "7.5", grade: str = "B") -> None:
    path.mkdir(parents=True, exist_ok=True)
    data = {
        "dimension": dim_name,
        "overallScore": score,
        "overallGrade": grade,
        "principles": [],
        "violations": [],
        "compliance": [],
    }
    (path / f"{dim_name}.json").write_text(json.dumps(data))


def _write_evidence(path: Path, dim_name: str, discipline: str = "typescript") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{dim_name}_evidence.json").write_text(
        json.dumps({"dimension": dim_name, "discipline": discipline})
    )


def _write_repo_info(project_dir: Path, parent: str | None = None) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    info: dict = {"name": project_dir.name}
    if parent is not None:
        info["parent"] = parent
    (project_dir / "repository_info.json").write_text(json.dumps(info))


def _setup_child(reports_root: Path, child_id: str, parent_id: str, dims: list[DimensionResult], run_id: str = "run1") -> None:
    """Create a child project directory with a single run containing the given dimensions."""
    child_dir = reports_root / child_id
    _write_repo_info(child_dir, parent=parent_id)
    for dim in dims:
        eval_dir = child_dir / run_id / "evaluation"
        _write_eval(eval_dir, dim.dimension, dim.overall_score or "7.5", dim.overall_grade or "B")
        evidence_dir = child_dir / run_id / "evidence"
        _write_evidence(evidence_dir, dim.dimension)


# ---------------------------------------------------------------------------
# _find_children
# ---------------------------------------------------------------------------

class TestFindChildren:
    def test_finds_children_by_parent_field(self, tmp_path: Path):
        root = tmp_path / "evaluations"
        parent_dir = root / "parent1"
        _write_repo_info(parent_dir)
        _write_repo_info(root / "child1", parent="parent1")
        _write_repo_info(root / "child2", parent="parent1")
        _write_repo_info(root / "other", parent="someone_else")

        children = _find_children(root, "parent1")
        assert sorted(children) == ["child1", "child2"]

    def test_no_children(self, tmp_path: Path):
        root = tmp_path / "evaluations"
        (root / "parent1").mkdir(parents=True)
        assert _find_children(root, "parent1") == []

    def test_skips_malformed_json(self, tmp_path: Path):
        root = tmp_path / "evaluations"
        (root / "parent1").mkdir(parents=True)
        child_dir = root / "child1"
        child_dir.mkdir(parents=True)
        (child_dir / "repository_info.json").write_text("not json")

        assert _find_children(root, "parent1") == []


# ---------------------------------------------------------------------------
# compute_accumulated — parent aggregation
# ---------------------------------------------------------------------------

class TestParentAccumulated:
    def test_parent_with_no_children_returns_none(self, tmp_path: Path):
        """A project with no runs and no children returns None."""
        root = tmp_path / "evaluations"
        (root / "lonely").mkdir(parents=True)
        result = compute_accumulated(str(root), "lonely", None)
        assert result is None

    def test_parent_with_children_returns_data(self, tmp_path: Path):
        """Parent with children that have runs returns aggregated data."""
        root = tmp_path / "evaluations"
        parent_id = "parent1"
        _write_repo_info(root / parent_id)

        _setup_child(root, "child1", parent_id, [_dim("maintainability", "8.0", "A")])
        _setup_child(root, "child2", parent_id, [_dim("security", "6.0", "C")])

        result = compute_accumulated(str(root), parent_id, None)
        assert result is not None
        assert result["project"] == parent_id
        assert result["summary"]["dimensionCount"] == 2
        dim_names = sorted(d["dimension"] for d in result["dimensions"])
        assert dim_names == ["maintainability", "security"]
        assert result["summary"]["numericAverage"] == 7.0

    def test_parent_with_children_no_runs_returns_none(self, tmp_path: Path):
        """Parent whose children have no runs returns None."""
        root = tmp_path / "evaluations"
        parent_id = "parent1"
        _write_repo_info(root / parent_id)
        _write_repo_info(root / "child1", parent=parent_id)

        result = compute_accumulated(str(root), parent_id, None)
        assert result is None

    def test_parent_merges_same_dimension_from_multiple_children(self, tmp_path: Path):
        """When multiple children evaluate the same dimension, both appear."""
        root = tmp_path / "evaluations"
        parent_id = "parent1"
        _write_repo_info(root / parent_id)

        _setup_child(root, "child1", parent_id, [_dim("maintainability", "8.0", "A")])
        _setup_child(root, "child2", parent_id, [_dim("maintainability", "6.0", "C")])

        result = compute_accumulated(str(root), parent_id, None)
        assert result is not None
        assert result["summary"]["dimensionCount"] == 2
        assert result["summary"]["numericAverage"] == 7.0
