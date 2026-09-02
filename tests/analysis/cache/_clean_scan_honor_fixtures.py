"""Shared fixtures for tests/analysis/cache/test_clean_scan_honor_*.py siblings.

Split out of test_clean_scan_honor.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import CacheEntry, LocalFileBackend, build_cache_key_for_file
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest


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
    from quodeq.analysis._types import _AnalysisContext
    return _AnalysisContext(
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
        _build_dimension_prompt,
        _parse_dimension_evidence,
        _run_dimension_analysis,
    )
    from quodeq.analysis.subagents.runner import DimensionCallbacks
    return DimensionCallbacks(
        build_prompt=_build_dimension_prompt,
        run_analysis=_run_dimension_analysis,
        parse_evidence=_parse_dimension_evidence,
    )
