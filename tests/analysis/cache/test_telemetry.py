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

from quodeq.analysis.run_types import AnalysisOptions, RunConfig, AnalysisContext
from quodeq.analysis.cache import (
    CacheEntry, LocalFileBackend, build_cache_key_for_file,
)
from quodeq.analysis.cache.dimension_runner import CacheRunOptions, process_dimension_with_cache
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


def _make_ctx() -> AnalysisContext:
    from quodeq.analysis._dimensions import DimensionsConfig
    return AnalysisContext(
        dimensions_data=DimensionsConfig(dimensions={}),
        date_str="2026-01-01", template="", subagent_template="", total=1,
    )


def _make_callbacks():
    from quodeq.analysis._dimension_steps import (
        build_dimension_prompt, parse_dimension_evidence, run_dimension_analysis,
    )
    from quodeq.analysis.subagents.runner import DimensionCallbacks
    return DimensionCallbacks(
        build_prompt=build_dimension_prompt,
        run_analysis=run_dimension_analysis,
        parse_evidence=parse_dimension_evidence,
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
            "quodeq.analysis.cache._dimension_context.emit_marker",
            new=fake_emit,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(),
                opts=CacheRunOptions(callbacks=_make_callbacks(), cache=cache),
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

        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
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
            "quodeq.analysis.cache._dimension_context.emit_marker",
            new=fake_emit,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(),
                opts=CacheRunOptions(callbacks=_make_callbacks(), cache=cache, dispatcher=fake_dispatch),
            )

        cache_stats = [(p, kw) for p, kw in markers if p == "cache_stats"]
        assert len(cache_stats) == 1
        _, payload = cache_stats[0]
        assert payload["dimension"] == "security"
        assert payload["hits"] == 1
        assert payload["misses"] == 2
        assert payload["total"] == 3

    def test_clean_scan_marks_invalidated_mode(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Clean-scan runs include a 'mode' field so the dashboard can
        distinguish 'cache invalidated, forced re-analysis' from a
        regular cold run."""
        config = _setup(tmp_path, {"a.py": "x"})
        config.options.incremental = False  # clean scan

        markers: list[tuple] = []

        def fake_emit(phase, **kwargs):
            markers.append((phase, kwargs))

        from quodeq.core.evidence.model import Evidence

        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
            jsonl = cfg.work_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            jsonl.write_text('{"file": "a.py", "line": 1}\n')
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=1, files_read=1, coverage_pct=100.0,
                principles={},
            )

        with patch(
            "quodeq.analysis.cache._dimension_context.emit_marker",
            new=fake_emit,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(),
                opts=CacheRunOptions(callbacks=_make_callbacks(), cache=cache, dispatcher=fake_dispatch),
            )

        cache_stats = [(p, kw) for p, kw in markers if p == "cache_stats"]
        assert len(cache_stats) == 1
        _, payload = cache_stats[0]
        assert payload["mode"] == "clean-scan-invalidated"

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
            "quodeq.analysis.cache._dimension_context.emit_marker",
            new=fake_emit,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(),
                opts=CacheRunOptions(callbacks=_make_callbacks(), cache=cache),
            )

        # Round-trip the cache_stats payload through JSON.
        cache_stats = next(kw for p, kw in captured if p == "cache_stats")
        roundtripped = json.loads(json.dumps(cache_stats))
        assert roundtripped == cache_stats


class TestJsonlEvidenceProducedGate:
    """_try_parse_stream_evidence's mcp_produced check (private, inside
    _dimension_steps.parse_dimension_evidence) moved from
    ``jsonl_file.exists() and jsonl_file.stat().st_size > 0`` to
    ``evidence_file_size(jsonl_file) > 0`` (the run_files helper). Pin the
    branch choice for the three shapes that mattered under the old check:
    missing, present-but-empty, and present-with-content.

    Reaches ``parse_dimension_evidence`` via ``_make_callbacks()`` (already
    imported at module scope above) rather than a fresh import, so this adds
    no new private-module import for tools/private_imports_tests_baseline.txt
    to track.
    """

    def _parse_evidence_recording_branch(self, monkeypatch):
        parse_evidence = _make_callbacks().parse_evidence
        calls: list[str] = []
        monkeypatch.setitem(
            parse_evidence.__globals__, "count_files_from_stream",
            lambda *_a, **_k: calls.append("count") or 3,
        )
        monkeypatch.setitem(
            parse_evidence.__globals__, "extract_evidence_from_stream",
            lambda *_a, **_k: calls.append("extract") or 5,
        )
        return parse_evidence, calls

    def _valid_stream_file(self, tmp_path: Path) -> Path:
        stream_file = tmp_path / "d_live.stream"
        stream_file.write_text('{"type": "assistant"}\n')
        return stream_file

    def test_missing_jsonl_falls_back_to_stream_extraction(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        parse_evidence, calls = self._parse_evidence_recording_branch(monkeypatch)
        config = _setup(tmp_path, {})
        jsonl_file = tmp_path / "d_evidence.jsonl"  # never created

        parse_evidence(config, "d", self._valid_stream_file(tmp_path), jsonl_file, _make_ctx())

        assert calls == ["extract"]

    def test_empty_jsonl_falls_back_to_stream_extraction(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        parse_evidence, calls = self._parse_evidence_recording_branch(monkeypatch)
        config = _setup(tmp_path, {})
        jsonl_file = tmp_path / "d_evidence.jsonl"
        jsonl_file.write_text("")

        parse_evidence(config, "d", self._valid_stream_file(tmp_path), jsonl_file, _make_ctx())

        assert calls == ["extract"]

    def test_nonempty_jsonl_uses_stream_file_count(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        parse_evidence, calls = self._parse_evidence_recording_branch(monkeypatch)
        config = _setup(tmp_path, {})
        jsonl_file = tmp_path / "d_evidence.jsonl"
        jsonl_file.write_text('{"file": "a.py"}\n')

        parse_evidence(config, "d", self._valid_stream_file(tmp_path), jsonl_file, _make_ctx())

        assert calls == ["count"]
