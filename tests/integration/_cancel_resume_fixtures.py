"""Shared fixtures for tests/integration/test_cancel_resume_*.py siblings.

Split out of test_cancel_resume.py.

Composes the building blocks (per-file markers, per-dim state, V2 cache,
dispatch-keys sidecar, discard wipe, circuit breaker) by driving the dim
runner with a programmable fake dispatcher and the real cache backend.

No real subprocesses, no real network. The fake dispatcher writes a
scripted finding-and-marker stream into the dim's evidence JSONL the
same way the production pool does, so the cache layer, dim-state
writer, and breaker all see realistic input.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.manifest import AnalysisTarget, SourceManifest
from quodeq.analysis.subagents.runner import DimensionCallbacks
from quodeq.core.evidence.model import Evidence
from quodeq.shared import cancellation


@pytest.fixture(autouse=True)
def _reset_cancel():
    cancellation.reset()
    yield
    cancellation.reset()


def _make_manifest(file_names: list[str]) -> SourceManifest:
    target = AnalysisTarget(
        name="test", language="python",
        source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    return SourceManifest(targets=[target], total_files=len(file_names))


def _make_config(
    src: Path, *, work_dir: Path,
    file_names: list[str],
    threshold: int = 5,
) -> RunConfig:
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=work_dir,
        options=AnalysisOptions(
            subagent_model="test-model",
            failure_streak_threshold=threshold,
        ),
        manifest=_make_manifest(file_names),
    )


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


def _make_dummy_evidence(*, files_read: int) -> Evidence:
    return Evidence(
        repository="", language="python", date="2026-01-01",
        source_file_count=files_read, files_read=files_read,
        coverage_pct=100.0, principles={},
    )


def _setup_run(tmp_path: Path, files: list[str], threshold: int = 5):
    src = tmp_path / "src"
    src.mkdir()
    for name in files:
        (src / name).write_text(f"# {name}\n")
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    cache = LocalFileBackend(root=tmp_path / "cache")
    config = _make_config(src, work_dir=work_dir, file_names=files, threshold=threshold)
    return config, src, work_dir, cache


def _ok_marker(f: str) -> dict:
    return {"_marker": "file_done", "file": f, "status": "ok"}


def _err_marker(f: str, reason: str = "token_limit") -> dict:
    return {"_marker": "file_done", "file": f, "status": "error", "reason": reason}


def _finding(f: str) -> dict:
    return {"file": f, "line": 1, "t": "violation", "severity": "minor",
            "w": f"v-{f}", "reason": "r", "req": "X-1",
            "p": "Modularity", "d": "maintainability"}


class _ScriptedDispatcher:
    """Writes a caller-defined sequence of JSONL lines for each call."""

    def __init__(self, work_dir: Path, *, behavior: str = "ok_all"):
        self._work_dir = work_dir
        self._behavior = behavior
        self.calls: list[set[str]] = []

    def __call__(
        self, config: RunConfig, dim_id: str, idx: int, ctx, callbacks, **_,
    ) -> Evidence | None:
        files = sorted(config.options.incremental_file_filter or set())
        self.calls.append(set(files))
        jsonl = (config.work_dir or config.src) / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as out:
            for entry in self._script(files):
                out.write(json.dumps(entry) + "\n")
        # No sleep: the breaker does a final scan when the runner signals stop
        # (see FailureStreakWatcher._run), so a trip is detected deterministically
        # once dispatch returns -- it no longer depends on a poll landing during
        # dispatch. The old fixed sleep was a slow-runner flake ("DID NOT RAISE
        # CircuitBreakerError" on macos-latest).
        return _make_dummy_evidence(files_read=len(files))

    def _script(self, files: list[str]):
        if self._behavior == "ok_all":
            for f in files:
                yield _finding(f)
                yield _ok_marker(f)
        elif self._behavior == "first_two_ok_then_cancel":
            for f in files[:2]:
                yield _finding(f)
                yield _ok_marker(f)
            cancellation.request_cancel()
        elif self._behavior == "first_one_token_limit":
            yield _finding(files[0])
            yield _err_marker(files[0], "token_limit")
            for f in files[1:]:
                yield _finding(f)
                yield _ok_marker(f)
        elif self._behavior == "all_errors":
            for f in files:
                yield _err_marker(f, "token_limit")
        else:
            raise ValueError(f"unknown behavior: {self._behavior}")
