"""Shared fixtures for tests/analysis/cache/test_clean_scan_honor_*.py siblings.

Split out of test_clean_scan_honor.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis.run_types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import CacheEntry, LocalFileBackend, build_cache_key_for_file
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.core.evidence.model import Evidence


def _make_manifest(file_names: list[str]) -> SourceManifest:
    target = AnalysisTarget(
        name="test", language="python",
        source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    return SourceManifest(targets=[target], total_files=len(file_names))


def _setup(
    tmp_path: Path, contents: dict[str, str], *, incremental: bool = True,
) -> tuple[RunConfig, Path]:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for name, text in contents.items():
        (src / name).write_text(text)
    config = RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=tmp_path / "work",
        options=AnalysisOptions(subagent_model="test-model", incremental=incremental),
        manifest=_make_manifest(sorted(contents.keys())),
    )
    return config, src


def _make_ctx():
    from quodeq.analysis._dimensions import DimensionsConfig
    from quodeq.analysis.run_types import AnalysisContext
    return AnalysisContext(
        dimensions_data=DimensionsConfig(dimensions={}),
        date_str="2026-01-01", template="", subagent_template="", total=1,
    )


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache_v2")


def _populate_cache(cache, config, dim, files: list[str]) -> None:
    for f in files:
        key = build_cache_key_for_file(config, f, dim)
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{"file": f, "line": 1, "t": "violation", "w": f"cached-{f}"}],
            files_read=1, file_path=f, dimension=dim, model_id="test-model",
        ))


def _setup_cache_with_hits(
    tmp_path: Path, cache, contents: dict[str, str], dim: str, hit_files: list[str],
    *, incremental: bool = False,
) -> tuple[RunConfig, Path]:
    """Build a config + a populated cache in one call.

    Collapses the repeated ``_setup(...)`` + ``_populate_cache(...)`` pair
    that every clean-scan test in this module needs.
    """
    config, src = _setup(tmp_path, contents, incremental=incremental)
    _populate_cache(cache, config, dim, hit_files)
    return config, src


def _callbacks():
    """The standard DimensionCallbacks wiring used by every dispatch test here."""
    from quodeq.analysis._dimension_steps import (
        build_dimension_prompt,
        parse_dimension_evidence,
        run_dimension_analysis,
    )
    from quodeq.analysis.subagents.runner import DimensionCallbacks
    return DimensionCallbacks(
        build_prompt=build_dimension_prompt,
        run_analysis=run_dimension_analysis,
        parse_evidence=parse_dimension_evidence,
    )


def _build_evidence(*, source_file_count: int, files_read: int, coverage_pct: float) -> Evidence:
    """A minimal Evidence stub for the fake dispatchers in the clean-scan dispatch tests."""
    return Evidence(
        repository="", language="python", date="2026-01-01",
        source_file_count=source_file_count, files_read=files_read,
        coverage_pct=coverage_pct, principles={},
    )


def _write_dispatch_result(cfg, dim_id: str, entries: list[tuple[str, str]], *, mode: str = "a") -> None:
    """Append violation + file_done marker lines to a dimension's evidence.jsonl.

    Mirrors what a real subagent worker appends: one violation line per
    ``(file, weight)`` entry followed by its file_done marker.
    """
    jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open(mode) as out:
        for file, weight in entries:
            out.write(json.dumps({"file": file, "line": 1, "t": "violation", "w": weight}) + "\n")
            out.write(json.dumps({"_marker": "file_done", "file": file, "status": "ok"}) + "\n")
