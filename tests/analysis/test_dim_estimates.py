"""Tests for quodeq.analysis._dim_estimates — upfront per-dim file estimation.

After B6 the estimate is just the V2 cache-miss count per dimension.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.analysis._dim_estimates import (
    DIM_ESTIMATES_FILENAME,
    compute_dim_estimates,
    read_dim_estimates,
    write_dim_estimates,
)
from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import (
    CacheEntry, LocalFileBackend, build_cache_key_for_file,
)
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest


def _make_config(
    src: Path, file_names: list[str], *,
    incremental: bool = True, file_filter=None,
) -> RunConfig:
    target = AnalysisTarget(
        name="t", language="python", source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    manifest = SourceManifest(targets=[target], total_files=len(file_names))
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=src, manifest=manifest,
        options=AnalysisOptions(
            subagent_model="test-model",
            incremental=incremental,
            incremental_file_filter=file_filter,
        ),
    )


def _write_files(src: Path, names: list[str]) -> None:
    src.mkdir(parents=True, exist_ok=True)
    for n in names:
        (src / n).write_text(f"# {n}")


def _populate(cache: LocalFileBackend, config: RunConfig, dim: str, files: list[str]) -> None:
    for f in files:
        key = build_cache_key_for_file(config, f, dim)
        cache.put(key, CacheEntry(
            key=key, schema_version=1, findings=[],
            files_read=1, file_path=f, dimension=dim, model_id="test-model",
        ))


class TestComputeDimEstimates:
    def test_clean_scan_returns_full_count(self, tmp_path: Path):
        src = tmp_path / "src"
        _write_files(src, ["a.py", "b.py", "c.py"])
        config = _make_config(src, ["a.py", "b.py", "c.py"], incremental=False)

        result = compute_dim_estimates(config, ["security"])
        assert result["security"] == {"count": 3, "reason": "full", "total": 3, "cached": 0}

    def test_diff_mode_intersects_filter(self, tmp_path: Path):
        src = tmp_path / "src"
        _write_files(src, ["a.py", "b.py", "c.py"])
        config = _make_config(
            src, ["a.py", "b.py", "c.py"],
            incremental=False, file_filter={"a.py", "c.py"},
        )

        result = compute_dim_estimates(config, ["security"])
        assert result["security"] == {"count": 2, "reason": "diff", "total": 2, "cached": 0}

    def test_empty_dim_returns_zero_with_empty_reason(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        config = _make_config(src, [])

        result = compute_dim_estimates(config, ["security"])
        assert result["security"]["count"] == 0
        assert result["security"]["reason"] == "empty"
        assert result["security"]["total"] == 0
        assert result["security"]["cached"] == 0

    def test_incremental_first_run_all_misses(self, tmp_path: Path):
        src = tmp_path / "src"
        _write_files(src, ["a.py", "b.py"])
        config = _make_config(src, ["a.py", "b.py"], incremental=True)

        with patch(
            "quodeq.analysis._dim_estimates.LocalFileBackend",
            return_value=LocalFileBackend(root=tmp_path / "fresh-cache"),
        ):
            result = compute_dim_estimates(config, ["security"])
        assert result["security"] == {"count": 2, "reason": "first-run", "total": 2, "cached": 0}

    def test_incremental_partial_cache_marks_incremental(self, tmp_path: Path):
        src = tmp_path / "src"
        _write_files(src, ["a.py", "b.py", "c.py"])
        config = _make_config(src, ["a.py", "b.py", "c.py"], incremental=True)
        cache = LocalFileBackend(root=tmp_path / "fresh-cache")
        _populate(cache, config, "security", ["a.py", "b.py"])

        with patch(
            "quodeq.analysis._dim_estimates.LocalFileBackend",
            return_value=cache,
        ):
            result = compute_dim_estimates(config, ["security"])
        assert result["security"] == {"count": 1, "reason": "incremental", "total": 3, "cached": 2}

    def test_incremental_full_cache_returns_zero(self, tmp_path: Path):
        src = tmp_path / "src"
        _write_files(src, ["a.py"])
        config = _make_config(src, ["a.py"], incremental=True)
        cache = LocalFileBackend(root=tmp_path / "fresh-cache")
        _populate(cache, config, "security", ["a.py"])

        with patch(
            "quodeq.analysis._dim_estimates.LocalFileBackend",
            return_value=cache,
        ):
            result = compute_dim_estimates(config, ["security"])
        assert result["security"]["count"] == 0
        assert result["security"]["reason"] == "incremental"
        assert result["security"]["total"] == 1
        assert result["security"]["cached"] == 1


class TestPersistence:
    def test_write_and_read_round_trip(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        estimates = {
            "security": {"count": 3, "reason": "incremental", "total": 10, "cached": 7},
            "reliability": {"count": 0, "reason": "empty", "total": 0, "cached": 0},
        }
        write_dim_estimates(run_dir, estimates)
        loaded = read_dim_estimates(run_dir)
        assert loaded == estimates

    def test_read_missing_returns_empty(self, tmp_path: Path):
        assert read_dim_estimates(tmp_path / "nope") == {}

    def test_read_corrupt_returns_empty(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / DIM_ESTIMATES_FILENAME).write_text("{not json")
        assert read_dim_estimates(run_dir) == {}

    def test_read_legacy_int_format_normalises(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / DIM_ESTIMATES_FILENAME).write_text(json.dumps({"security": 5}))
        loaded = read_dim_estimates(run_dir)
        assert loaded == {"security": {"count": 5, "reason": "", "total": 5, "cached": 0}}

    def test_read_legacy_dict_without_coverage_fields_normalises(self, tmp_path: Path):
        # Runs from before the total/cached fields: total falls back to count,
        # cached to 0 — the UI then has no cached segment to draw.
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / DIM_ESTIMATES_FILENAME).write_text(
            json.dumps({"security": {"count": 5, "reason": "incremental"}})
        )
        loaded = read_dim_estimates(run_dir)
        assert loaded == {"security": {"count": 5, "reason": "incremental", "total": 5, "cached": 0}}


class TestFreshRunSafety:
    def test_dim_estimates_no_prior_state(self, tmp_path: Path):
        """A first run with cold cache must not raise."""
        src = tmp_path / "src"
        _write_files(src, ["a.py"])
        config = _make_config(src, ["a.py"], incremental=True)

        with patch(
            "quodeq.analysis._dim_estimates.LocalFileBackend",
            return_value=LocalFileBackend(root=tmp_path / "fresh-cache"),
        ):
            result = compute_dim_estimates(config, ["security", "reliability"])

        for dim in ("security", "reliability"):
            assert result[dim]["count"] == 1
            assert result[dim]["reason"] == "first-run"
