"""Cache telemetry — emit per-dim hit/miss markers for the dashboard.

The runner's marker mechanism (``emit_marker``) is the existing IPC
channel for status events. Adding a ``cache_stats`` phase lets the
dashboard / SSE stream surface live cache hit-rate without parsing
log lines.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig, _AnalysisContext
from quodeq.analysis.cache import (
    CacheEntry, LocalFileBackend, build_cache_key_for_file,
)
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest


def _setup(tmp_path: Path, contents: dict[str, str]) -> RunConfig:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for n, t in contents.items():
        (src / n).write_text(t)
    target = AnalysisTarget(
        name="t", language="python", source_files=sorted(contents.keys()),
        total_files=len(contents),
        language_stats={"py": len(contents)},
    )
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=tmp_path / "work",
        options=AnalysisOptions(subagent_model="test-model"),
        manifest=SourceManifest(targets=[target], total_files=len(contents)),
    )


def _make_ctx() -> _AnalysisContext:
    from quodeq.analysis._dimensions import DimensionsConfig
    return _AnalysisContext(
        dimensions_data=DimensionsConfig(dimensions={}),
        date_str="2026-01-01", template="", subagent_template="", total=1,
    )


def _make_callbacks():
    from quodeq.analysis._dimension_steps import (
        _build_dimension_prompt, _parse_dimension_evidence, _run_dimension_analysis,
    )
    from quodeq.analysis.subagents.runner import DimensionCallbacks
    return DimensionCallbacks(
        build_prompt=_build_dimension_prompt,
        run_analysis=_run_dimension_analysis,
        parse_evidence=_parse_dimension_evidence,
    )


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


# ============================================================
# Marker emission
# ============================================================


class TestCacheStatsMarker:
    def test_all_hits_emits_zero_misses(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        config = _setup(tmp_path, {"a.py": "x", "b.py": "y"})
        for f in ("a.py", "b.py"):
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=1, findings=[],
                files_read=1, file_path=f, dimension="security",
                model_id="test-model",
            ))

        markers: list[tuple] = []
        def fake_emit(phase, **kwargs):
            markers.append((phase, kwargs))

        with patch(
            "quodeq.analysis.cache.dimension_runner.emit_marker",
            new=fake_emit,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(),
                cache=cache,
            )

        cache_stats = [(p, kw) for p, kw in markers if p == "cache_stats"]
        assert len(cache_stats) == 1
        _, payload = cache_stats[0]
        assert payload["dimension"] == "security"
        assert payload["hits"] == 2
        assert payload["misses"] == 0
        assert payload["total"] == 2

    def test_partial_hits_emits_correct_split(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        config = _setup(tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"})
        # Only b.py is cached.
        key_b = build_cache_key_for_file(config, "b.py", "security")
        cache.put(key_b, CacheEntry(
            key=key_b, schema_version=1, findings=[{"file": "b.py"}],
            files_read=1, file_path="b.py", dimension="security",
            model_id="test-model",
        ))

        markers: list[tuple] = []
        def fake_emit(phase, **kwargs):
            markers.append((phase, kwargs))

        from quodeq.core.evidence.model import Evidence
        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks):
            jsonl = cfg.work_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            jsonl.write_text(
                '{"file": "a.py", "line": 1}\n{"file": "c.py", "line": 1}\n'
            )
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=2, files_read=2, coverage_pct=100.0,
                principles={},
            )

        with patch(
            "quodeq.analysis.cache.dimension_runner.emit_marker",
            new=fake_emit,
        ), patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=fake_dispatch,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(),
                cache=cache,
            )

        cache_stats = [(p, kw) for p, kw in markers if p == "cache_stats"]
        assert len(cache_stats) == 1
        _, payload = cache_stats[0]
        assert payload["dimension"] == "security"
        assert payload["hits"] == 1
        assert payload["misses"] == 2
        assert payload["total"] == 3

    def test_clean_scan_marks_refresh_mode(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Clean-scan runs include a 'mode' field so the dashboard can
        distinguish 'fresh forced re-analysis' from a regular cold run."""
        config = _setup(tmp_path, {"a.py": "x"})
        config.options.incremental = False  # clean scan

        markers: list[tuple] = []
        def fake_emit(phase, **kwargs):
            markers.append((phase, kwargs))

        from quodeq.core.evidence.model import Evidence
        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks):
            jsonl = cfg.work_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            jsonl.write_text('{"file": "a.py", "line": 1}\n')
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=1, files_read=1, coverage_pct=100.0,
                principles={},
            )

        with patch(
            "quodeq.analysis.cache.dimension_runner.emit_marker",
            new=fake_emit,
        ), patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=fake_dispatch,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(),
                cache=cache,
            )

        cache_stats = [(p, kw) for p, kw in markers if p == "cache_stats"]
        assert len(cache_stats) == 1
        _, payload = cache_stats[0]
        assert payload["mode"] == "clean-scan-refresh"

    def test_marker_payload_is_json_serializable(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Marker payload must be JSON-serializable since emit_marker
        passes it to json.dumps for IPC over stdout."""
        config = _setup(tmp_path, {"a.py": "x"})
        for f in ("a.py",):
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=1, findings=[],
                files_read=1, file_path=f, dimension="security",
                model_id="test-model",
            ))

        captured = []
        def fake_emit(phase, **kwargs):
            captured.append((phase, kwargs))

        with patch(
            "quodeq.analysis.cache.dimension_runner.emit_marker",
            new=fake_emit,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(),
                cache=cache,
            )

        # Round-trip the cache_stats payload through JSON.
        cache_stats = next(kw for p, kw in captured if p == "cache_stats")
        roundtripped = json.loads(json.dumps(cache_stats))
        assert roundtripped == cache_stats
