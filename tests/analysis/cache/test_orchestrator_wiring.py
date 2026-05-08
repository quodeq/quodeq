"""V2 fast-path at the incremental orchestrator level.

The B5 wiring sits below V1's incremental short-circuit (when nothing
changed, V1 returns from JSONL without invoking _process_single_dimension,
so V2 was never consulted). This test suite pins down a higher wiring
point in run_dimension_incremental:

  - When cache fully covers the dimension, return immediately without
    calling V1's classify_files / change detection
  - When any file misses, return None and let V1's path run
  - When the flag is off, V1 always runs unchanged
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig, _AnalysisContext
from quodeq.analysis.cache import CacheEntry, LocalFileBackend, build_cache_key_for_file
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest


# ============================================================
# Fixtures (mirrors test_dimension_runner.py)
# ============================================================


def _make_manifest(file_names: list[str]) -> SourceManifest:
    target = AnalysisTarget(
        name="test", language="python",
        source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    return SourceManifest(targets=[target], total_files=len(file_names))


def _setup(
    tmp_path: Path, contents: dict[str, str],
) -> tuple[RunConfig, Path]:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for name, text in contents.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    config = RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=tmp_path / "work",
        options=AnalysisOptions(subagent_model="test-model"),
        manifest=_make_manifest(sorted(contents.keys())),
    )
    return config, src


def _make_ctx() -> _AnalysisContext:
    from quodeq.analysis._dimensions import DimensionsConfig
    return _AnalysisContext(
        dimensions_data=DimensionsConfig(dimensions={}),
        date_str="2026-01-01", template="", subagent_template="", total=1,
    )


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache_v2")


def _populate_cache(
    cache: LocalFileBackend, config: RunConfig, dim: str,
    file_findings: dict[str, list[dict]],
) -> None:
    """Pre-populate the cache with given findings per file."""
    for f, findings in file_findings.items():
        key = build_cache_key_for_file(config, f, dim)
        cache.put(key, CacheEntry(
            key=key, schema_version=1, findings=findings,
            files_read=1, file_path=f, dimension=dim,
            model_id="test-model",
        ))


# ============================================================
# Fast-path tests
# ============================================================


class TestFullHitFastPath:
    def test_all_hits_skip_v1_classify_entirely(
        self, tmp_path: Path, cache: LocalFileBackend,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """The whole point of B5b: when cache fully covers a dimension,
        V1's classify_files / change detection / carry-forward must not run."""
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})
        _populate_cache(cache, config, "security", {
            "a.py": [{"file": "a.py", "line": 1, "t": "violation"}],
            "b.py": [{"file": "b.py", "line": 2, "t": "compliance"}],
        })

        monkeypatch.setenv("QUODEQ_CACHE_V2", "1")

        from quodeq.analysis import _incremental_orchestrator as orch

        with patch.object(orch, "classify_files") as mock_classify, \
             patch(
                "quodeq.analysis.cache.dimension_runner.LocalFileBackend",
                return_value=cache,
             ), patch(
                "quodeq.analysis._incremental_orchestrator.LocalFileBackend",
                return_value=cache,
             ):
            ev = orch.run_dimension_incremental(config, "security", 1, _make_ctx())

        # V1's classify_files must NOT have been called.
        mock_classify.assert_not_called()
        assert ev is not None

        # Final JSONL contains the cached findings.
        jsonl = (config.work_dir / "security_evidence.jsonl").read_text()
        files_in_jsonl = {json.loads(l)["file"] for l in jsonl.splitlines() if l.strip()}
        assert files_in_jsonl == {"a.py", "b.py"}

    def test_partial_cache_falls_through_to_v1(
        self, tmp_path: Path, cache: LocalFileBackend,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """When any file misses, V1 must take over so it can dispatch."""
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})
        # Only a.py is cached; b.py misses.
        _populate_cache(cache, config, "security", {
            "a.py": [{"file": "a.py", "line": 1}],
        })

        monkeypatch.setenv("QUODEQ_CACHE_V2", "1")

        from quodeq.analysis import _incremental_orchestrator as orch

        v1_called = {"hit": False}
        def fake_classify(*args, **kwargs):
            v1_called["hit"] = True
            from quodeq.analysis.incremental import FileClassification
            return FileClassification(to_analyze=[], unchanged={"a.py", "b.py"})

        with patch.object(orch, "classify_files", side_effect=fake_classify), \
             patch(
                "quodeq.analysis._incremental_orchestrator.LocalFileBackend",
                return_value=cache,
             ), patch(
                "quodeq.analysis._incremental_orchestrator._maybe_carry_forward",
             ), patch(
                "quodeq.analysis._incremental_orchestrator._run_phase1_analysis",
                return_value=None,
             ), patch(
                "quodeq.analysis._incremental_orchestrator.run_backfill_phase",
                return_value=set(),
             ), patch(
                "quodeq.analysis._incremental_orchestrator._finalize_incremental",
                return_value=None,
             ):
            orch.run_dimension_incremental(config, "security", 1, _make_ctx())

        assert v1_called["hit"] is True

    def test_flag_off_v1_always_runs(
        self, tmp_path: Path, cache: LocalFileBackend,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Cache fully populated but flag off → V1 still runs (no V2 fast-path)."""
        config, src = _setup(tmp_path, {"a.py": "x"})
        _populate_cache(cache, config, "security", {
            "a.py": [{"file": "a.py", "line": 1}],
        })

        monkeypatch.delenv("QUODEQ_CACHE_V2", raising=False)

        from quodeq.analysis import _incremental_orchestrator as orch

        v1_called = {"hit": False}
        def fake_classify(*args, **kwargs):
            v1_called["hit"] = True
            from quodeq.analysis.incremental import FileClassification
            return FileClassification(to_analyze=[], unchanged={"a.py"})

        with patch.object(orch, "classify_files", side_effect=fake_classify), \
             patch(
                "quodeq.analysis._incremental_orchestrator._maybe_carry_forward",
             ), patch(
                "quodeq.analysis._incremental_orchestrator._run_phase1_analysis",
                return_value=None,
             ), patch(
                "quodeq.analysis._incremental_orchestrator.run_backfill_phase",
                return_value=set(),
             ), patch(
                "quodeq.analysis._incremental_orchestrator._finalize_incremental",
                return_value=None,
             ):
            orch.run_dimension_incremental(config, "security", 1, _make_ctx())

        assert v1_called["hit"] is True

    def test_all_hits_writes_v1_compatible_fingerprint(
        self, tmp_path: Path, cache: LocalFileBackend,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """V2 fast-path must keep V1's fingerprint state consistent so that
        flipping the flag off later doesn't trigger an unnecessary
        full-reanalysis."""
        config, src = _setup(tmp_path, {"a.py": "x"})
        _populate_cache(cache, config, "security", {
            "a.py": [{"file": "a.py", "line": 1}],
        })

        monkeypatch.setenv("QUODEQ_CACHE_V2", "1")

        from quodeq.analysis import _incremental_orchestrator as orch

        with patch(
            "quodeq.analysis._incremental_orchestrator.LocalFileBackend",
            return_value=cache,
        ):
            orch.run_dimension_incremental(config, "security", 1, _make_ctx())

        # V1 fingerprint file should exist alongside V2 cache state.
        fp_path = config.work_dir / "security_fingerprint.json"
        assert fp_path.is_file(), "V1 fingerprint not written after V2 fast-path"
