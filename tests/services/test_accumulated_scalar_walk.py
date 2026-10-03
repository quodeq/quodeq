"""The cross-run walk and the card summary read non-winning runs as scalars.

After a score-cache epoch bump every run misses at once; reading each run's
every finding to learn its score made the rebuild cost minutes and gigabytes.
Event-log runs with evaluation reports are read from their grade tables, and
only the runs that win a dimension are read in full. These tests pin that,
and pin the fallbacks that keep the answer identical to a full read.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from quodeq.data.fs.report_parser.runs import read_run_data
from quodeq.services.accumulated import (
    clear_accumulated_process_cache, compute_accumulated, read_scalar_dimensions, slim_dimensions,
)
from tests.api._scores_routes_helpers import _scorable_violations, _seed_run

_PROJECT = "proj"


def _seed_reported_run(root: Path, run_id: str, n: int, *, files_read: int = 40) -> Path:
    """An event-log run with its grade tables and a matching evaluation report."""
    run_dir = _seed_run(root, _PROJECT, run_id, _scorable_violations(n))
    with sqlite3.connect(run_dir / "evaluation.db") as conn:
        conn.execute("UPDATE dimension_scores SET files_read = ?", (files_read,))
        (dim, score, grade) = conn.execute("SELECT dimension, score, grade FROM dimension_scores").fetchone()
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir()
    (eval_dir / f"{dim}.json").write_text(json.dumps({
        "dimension": dim, "overallScore": f"{score}/10", "overallGrade": grade,
        "filesRead": files_read, "principles": [], "violations": [], "compliance": [],
    }), encoding="utf-8")
    (run_dir / "evidence").mkdir(exist_ok=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    (run_dir / "scan.json").write_text("{}")
    return run_dir


@pytest.fixture(autouse=True)
def _clear_process_cache():
    clear_accumulated_process_cache()


@pytest.fixture
def full_reads(monkeypatch):
    """Run ids read in full, through every path the walk and hydration use."""
    from quodeq.data.fs.report_parser import runs as runs_mod

    calls: list[str] = []
    real = runs_mod.read_run_data

    def _counted(reports_root, project, run_id):
        calls.append(run_id)
        return real(reports_root, project, run_id)

    monkeypatch.setattr("quodeq.services.cache.read_run_data", _counted)
    monkeypatch.setattr("quodeq.services._accumulated_data.read_run_data", _counted)
    return calls


def test_a_cold_walk_reads_only_the_winning_run_in_full(tmp_path, full_reads):
    root = tmp_path / "evaluations"
    run_ids = [f"2026070{i}" for i in range(1, 7)]
    for i, rid in enumerate(run_ids):
        _seed_reported_run(root, rid, 5 + i)

    result = compute_accumulated(str(root), _PROJECT, None)

    assert result is not None and result["dimensions"]
    assert set(full_reads) == {max(run_ids)}, f"full reads: {sorted(set(full_reads))}"


def test_a_zero_files_read_run_is_read_in_full(tmp_path, full_reads):
    root = tmp_path / "evaluations"
    _seed_reported_run(root, "20260701", 5)
    _seed_reported_run(root, "20260702", 6, files_read=0)

    read_scalar_dimensions(root, _PROJECT, "20260702")

    assert full_reads == ["20260702"]


def test_a_run_without_reports_is_read_in_full(tmp_path, full_reads):
    root = tmp_path / "evaluations"
    _seed_run(root, _PROJECT, "20260701", _scorable_violations(5))

    assert read_scalar_dimensions(root, _PROJECT, "20260701") == []
    assert full_reads == ["20260701"]


def test_the_scalar_read_matches_the_full_read_on_what_selection_uses(tmp_path):
    root = tmp_path / "evaluations"
    _seed_reported_run(root, "20260701", 7)

    (scalar,) = read_scalar_dimensions(root, _PROJECT, "20260701")
    (full,) = slim_dimensions(read_run_data(root, _PROJECT, "20260701"))

    picked = ("dimension", "overall_score", "overall_grade", "files_read")
    assert {f: getattr(scalar, f) for f in picked} == {f: getattr(full, f) for f in picked}
