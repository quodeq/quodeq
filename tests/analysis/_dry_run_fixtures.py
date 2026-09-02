"""Shared helpers for tests/analysis/test_dry_run_*.py siblings.

Split out of test_dry_run.py.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis._types import AnalysisOptions, RunConfig


def _make_dims_data(*dimension_ids: str) -> dict:
    return {"applies": [{"id": d} for d in dimension_ids]}


def _make_config(tmp_path: Path, *, dry_run: bool = False, dimensions: list[str] | None = None) -> RunConfig:
    return RunConfig(
        src=tmp_path / "src",
        language="python",
        work_dir=tmp_path / "evidence",
        dimensions_data=_make_dims_data("security", "reliability"),
        options=AnalysisOptions(
            dry_run=dry_run,
            dimensions=dimensions,
        ),
    )
