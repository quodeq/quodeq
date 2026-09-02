"""Shared fixtures and test doubles for the test_dimension_runner* siblings.

process_dimension_with_cache — V2 dimension processor. Composes the B4
helpers (classify, persist, key) with the existing dispatcher boundary
(process_dimension_with_subagents) into a cache-aware dimension runner.
This module holds the scaffolding shared across the split test files:
manifest/config builders, the FakeDispatcher stand-in for the dispatcher
boundary, and small test doubles (log handler, slow-persist cache wrapper).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.analysis.subagents.runner import DimensionCallbacks
from quodeq.core.evidence.model import Evidence


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


def _make_ctx():
    from quodeq.analysis._dimensions import DimensionsConfig
    from quodeq.analysis._types import _AnalysisContext
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
        self, config: RunConfig, dim_id: str, idx: int, ctx, callbacks, **_,
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
                out.write(json.dumps({
                    "_marker": "file_done", "file": f, "status": "ok",
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


class _ListHandler(logging.Handler):
    """Capture log messages off a specific logger. The ``quodeq`` logger sets
    propagate=False, so pytest's caplog (root) can't see these records — we
    attach directly to the module logger instead."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class _SlowPutCache:
    """Wraps a real cache backend; ``put`` blocks on a release Event.

    Lets a test hold the FINAL persist tick in flight while it asserts
    that the watcher thread hasn't been abandoned yet, then release it
    and confirm the entry lands anyway.
    """

    def __init__(self, inner: LocalFileBackend, started: threading.Event,
                 release: threading.Event) -> None:
        self._inner = inner
        self._started = started
        self._release = release

    def get(self, key):
        return self._inner.get(key)

    def put(self, key, entry) -> None:
        self._started.set()
        # Safety net timeout so a broken test fails fast instead of hanging
        # the suite; the test itself sets `release` well before this.
        self._release.wait(timeout=5.0)
        self._inner.put(key, entry)

    def has(self, key) -> bool:
        return self._inner.has(key)

    def delete(self, key) -> None:
        self._inner.delete(key)

    def stats(self):
        return self._inner.stats()
