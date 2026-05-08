"""process_dimension_with_cache — V2 dimension processor.

Composes the B4 helpers (classify, persist, key) with the existing
dispatcher boundary (process_dimension_with_subagents) into a
cache-aware dimension runner.

These tests pin down the orchestration:

  - all-hits short-circuits dispatch entirely
  - all-misses dispatches with the original file set
  - partial dispatches with file filter restricted to misses
  - missed-file findings are persisted to cache after dispatch
  - cached findings are merged into final Evidence
  - dispatcher returning None propagates without writing cache entries

The dispatcher is patched at the boundary
(process_dimension_with_subagents) so we don't need a real subagent
pool. The runner's behaviour is fully observable through the cache
state and the dispatcher call recorder.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig, _AnalysisContext
from quodeq.analysis.cache import (
    CacheEntry,
    LocalFileBackend,
    build_cache_key_for_file,
)
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.analysis.subagents.runner import DimensionCallbacks
from quodeq.core.evidence.model import Evidence


# ============================================================
# Test scaffolding
# ============================================================


def _make_manifest(file_names: list[str]) -> SourceManifest:
    """Manifest with a single Python target listing the given files."""
    target = AnalysisTarget(
        name="test", language="python",
        source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    return SourceManifest(targets=[target], total_files=len(file_names))


def _make_config(
    src: Path, *, work_dir: Path | None = None,
    file_names: list[str] | None = None,
) -> RunConfig:
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=work_dir or src,
        options=AnalysisOptions(subagent_model="test-model"),
        manifest=_make_manifest(file_names or []) if file_names is not None else None,
    )


def _write_files(root: Path, contents: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _setup(
    tmp_path: Path, contents: dict[str, str] | None = None,
) -> tuple[RunConfig, Path]:
    """Create files + a config wired with a manifest. Returns (config, src)."""
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    if contents:
        _write_files(src, contents)
    config = _make_config(
        src, work_dir=tmp_path / "work",
        file_names=sorted(contents.keys()) if contents else [],
    )
    return config, src


def _make_ctx() -> _AnalysisContext:
    from quodeq.analysis._dimensions import DimensionsConfig
    return _AnalysisContext(
        dimensions_data=DimensionsConfig(dimensions={}),
        date_str="2026-01-01",
        template="",
        subagent_template="",
        total=1,
    )


def _make_callbacks() -> DimensionCallbacks:
    """Real callbacks aren't needed when the dispatcher boundary is mocked."""
    from quodeq.analysis._dimension_steps import (
        _build_dimension_prompt,
        _parse_dimension_evidence,
        _run_dimension_analysis,
    )
    return DimensionCallbacks(
        build_prompt=_build_dimension_prompt,
        run_analysis=_run_dimension_analysis,
        parse_evidence=_parse_dimension_evidence,
    )


class FakeDispatcher:
    """Stand-in for process_dimension_with_subagents that writes a JSONL
    and returns a synthetic Evidence — same contract as the real thing."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.calls: list[RunConfig] = []

    def __call__(
        self, config: RunConfig, dim_id: str, idx: int, ctx, callbacks,
    ) -> Evidence | None:
        self.calls.append(config)
        # Mirror what the real dispatcher does: write findings to JSONL
        # for each file in the (filtered) file list. Findings are
        # deterministic per file so we can assert on them.
        evidence_dir = config.work_dir or config.src
        jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        files_to_dispatch = (
            sorted(config.options.incremental_file_filter)
            if config.options.incremental_file_filter
            else self._all_source_files()
        )
        with jsonl.open("a") as out:
            for f in files_to_dispatch:
                out.write(json.dumps({
                    "file": f, "line": 1, "t": "violation", "w": f"v-{f}",
                }) + "\n")
        return _make_dummy_evidence(files_read=len(files_to_dispatch))

    def _all_source_files(self) -> list[str]:
        return sorted(
            str(p.relative_to(self.project_root))
            for p in self.project_root.rglob("*.py")
        )


def _make_dummy_evidence(*, files_read: int) -> Evidence:
    """Minimal Evidence shape — the V2 runner re-parses from JSONL anyway,
    so the dispatcher's exact return value isn't what matters."""
    return Evidence(
        repository="", language="python", date="2026-01-01",
        source_file_count=files_read, files_read=files_read,
        coverage_pct=100.0, principles={},
    )


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


# ============================================================
# Behavioural tests
# ============================================================


class TestAllHits:
    def test_all_hits_skip_dispatch_entirely(self, tmp_path: Path, cache: LocalFileBackend):
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        # Pre-populate cache for both files.
        for f, finding_text in [("a.py", "a-cached"), ("b.py", "b-cached")]:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=1,
                findings=[{"file": f, "line": 1, "t": "violation", "w": finding_text}],
                files_read=1, file_path=f, dimension="security",
                model_id="test-model",
            ))

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        # No dispatch happened.
        assert dispatcher.calls == []
        assert ev is not None

        # Final JSONL contains exactly the cached findings.
        jsonl = (tmp_path / "work" / "security_evidence.jsonl").read_text()
        lines = [json.loads(l) for l in jsonl.splitlines() if l.strip()]
        assert {l["w"] for l in lines} == {"a-cached", "b-cached"}


class TestAllMisses:
    def test_cold_cache_dispatches_all_files(self, tmp_path: Path, cache: LocalFileBackend):
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        # Dispatch happened with all files (file filter == all source files).
        assert len(dispatcher.calls) == 1
        dispatched = dispatcher.calls[0].options.incremental_file_filter
        assert dispatched == {"a.py", "b.py"}
        assert ev is not None

        # Cache entries written for both files after dispatch.
        for f in ["a.py", "b.py"]:
            key = build_cache_key_for_file(config, f, "security")
            entry = cache.get(key)
            assert entry is not None, f"no cache entry for {f}"
            assert entry.findings, f"empty findings for {f}"

    def test_second_run_after_cold_is_all_hits(self, tmp_path: Path, cache: LocalFileBackend):
        """Sanity end-to-end: cold run populates cache, second run hits."""
        config, src = _setup(tmp_path, {"a.py": "x"})

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            )
            # Run 2 — should not dispatch.
            dispatcher.calls.clear()
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            )
        assert dispatcher.calls == []


class TestPartialHits:
    def test_dispatches_only_misses(self, tmp_path: Path, cache: LocalFileBackend):
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"})

        # Pre-populate b.py only.
        key_b = build_cache_key_for_file(config, "b.py", "security")
        cache.put(key_b, CacheEntry(
            key=key_b, schema_version=1,
            findings=[{"file": "b.py", "line": 1, "t": "violation", "w": "b-cached"}],
            files_read=1, file_path="b.py", dimension="security",
            model_id="test-model",
        ))

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            )

        # Dispatcher saw only the misses.
        assert len(dispatcher.calls) == 1
        dispatched = dispatcher.calls[0].options.incremental_file_filter
        assert dispatched == {"a.py", "c.py"}
        assert ev is not None

        # Final JSONL combines miss findings + cached findings.
        jsonl = (tmp_path / "work" / "security_evidence.jsonl").read_text()
        lines = [json.loads(l) for l in jsonl.splitlines() if l.strip()]
        files_in_jsonl = {l["file"] for l in lines}
        assert files_in_jsonl == {"a.py", "b.py", "c.py"}

        # b.py's cached finding survived; a.py and c.py were freshly dispatched.
        b_findings = [l for l in lines if l["file"] == "b.py"]
        assert any(l["w"] == "b-cached" for l in b_findings)


class TestDispatchFailure:
    def test_dispatcher_returns_none_no_cache_writes(self, tmp_path: Path, cache: LocalFileBackend):
        config, src = _setup(tmp_path, {"a.py": "x"})

        def failing_dispatcher(*args, **kwargs):
            return None

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=failing_dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            )
        assert ev is None

        # No cache entry was written for the failed dispatch.
        key = build_cache_key_for_file(config, "a.py", "security")
        assert cache.get(key) is None


class TestNoSourceFiles:
    def test_falls_through_to_dispatcher_when_no_files(self, tmp_path: Path, cache: LocalFileBackend):
        # Empty src — the cache layer can't classify, defer to dispatcher.
        config, src = _setup(tmp_path, {})

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            )
        # Dispatcher was called (even with no files — same as V1 behaviour).
        assert len(dispatcher.calls) == 1


# ============================================================
# Wiring smoke test
# ============================================================


class TestFlagWiring:
    def test_v2_flag_routes_to_cache_runner(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """When QUODEQ_CACHE_V2=1, _process_single_dimension dispatches
        through the cache runner instead of calling subagents directly."""
        from quodeq.analysis._dimension_ops import _process_single_dimension

        config, src = _setup(tmp_path, {"a.py": "x"})

        monkeypatch.setenv("QUODEQ_CACHE_V2", "1")

        called_v2 = {"hit": False}
        def fake_v2(config, dim_id, idx, ctx, callbacks, cache=None):
            called_v2["hit"] = True
            return _make_dummy_evidence(files_read=1)

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_cache",
            new=fake_v2,
        ), patch(
            "quodeq.analysis._dimension_ops._save_dimension_fingerprint",
        ):
            _process_single_dimension(config, "security", 1, _make_ctx(), emit_log=False)

        assert called_v2["hit"] is True

    def test_v2_flag_off_routes_to_subagents_directly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Default behaviour: flag off → existing path, no V2 involvement."""
        from quodeq.analysis._dimension_ops import _process_single_dimension

        config, src = _setup(tmp_path, {"a.py": "x"})

        monkeypatch.delenv("QUODEQ_CACHE_V2", raising=False)

        called_v2 = {"hit": False}
        called_v1 = {"hit": False}
        def fake_v2(*args, **kwargs):
            called_v2["hit"] = True
            return _make_dummy_evidence(files_read=1)
        def fake_v1(*args, **kwargs):
            called_v1["hit"] = True
            return _make_dummy_evidence(files_read=1)

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_cache",
            new=fake_v2,
        ), patch(
            "quodeq.analysis._dimension_ops.process_dimension_with_subagents",
            new=fake_v1,
        ), patch(
            "quodeq.analysis._dimension_ops._save_dimension_fingerprint",
        ):
            _process_single_dimension(config, "security", 1, _make_ctx(), emit_log=False)

        assert called_v1["hit"] is True
        assert called_v2["hit"] is False
