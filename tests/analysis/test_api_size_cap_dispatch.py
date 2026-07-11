"""The API-provider file-size cap must be enforced at enumeration, not
silently at dispatch (the perpetual-97%-coverage bug).

Bug: ``_gather_api_source_files`` dropped files over ``QUODEQ_MAX_API_FILE_SIZE``
*after* taking them from the queue, without writing any ``file_done`` marker.
The files never entered the cache, so every incremental run re-counted them as
misses, re-queued them, and re-skipped them. The same ~3% of files haunted
every run and dim coverage never reached 100%.

The fix has one rule: the queue builder / estimates (``_list_source_files``)
and the dispatch-time worker must share ONE dispatchability predicate
(``quodeq.analysis.dispatch_policy``), and any file the worker still drops
must leave an explicit ``skipped`` marker behind.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._dim_estimates import compute_dim_estimates
from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.analysis.subagents._source_files import _list_source_files

CAP = 200  # small test cap, applied via QUODEQ_MAX_API_FILE_SIZE


def _make_config(src: Path, file_names: list[str]) -> RunConfig:
    target = AnalysisTarget(
        name="t", language="python", source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    manifest = SourceManifest(targets=[target], total_files=len(file_names))
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=src, manifest=manifest,
        options=AnalysisOptions(subagent_model="test-model", incremental=False),
    )


def _write_repo(src: Path) -> None:
    """One dispatchable file, one over the cap."""
    src.mkdir(parents=True, exist_ok=True)
    (src / "small.py").write_text("# small\n")
    (src / "big.py").write_text("# big\n" + "x = 1\n" * CAP)


@pytest.fixture
def api_provider(monkeypatch):
    monkeypatch.setenv("QUODEQ_MAX_API_FILE_SIZE", str(CAP))
    with patch("quodeq.analysis.dispatch_policy.provider_is_api", return_value=True):
        yield


@pytest.fixture
def cli_provider(monkeypatch):
    monkeypatch.setenv("QUODEQ_MAX_API_FILE_SIZE", str(CAP))
    with patch("quodeq.analysis.dispatch_policy.provider_is_api", return_value=False):
        yield


class TestEnumerationAppliesCap:
    def test_list_source_files_excludes_oversized_for_api_provider(
        self, tmp_path: Path, api_provider,
    ):
        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])

        files, _ext, excluded = _list_source_files(config, "security")

        assert files == ["small.py"]
        assert excluded == ["big.py"]

    def test_list_source_files_keeps_oversized_for_cli_provider(
        self, tmp_path: Path, cli_provider,
    ):
        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])

        files, _ext, excluded = _list_source_files(config, "security")

        assert sorted(files) == ["big.py", "small.py"]
        assert excluded == []

    def test_dim_estimates_totals_exclude_oversized(self, tmp_path: Path, api_provider):
        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])

        result = compute_dim_estimates(config, ["security"])

        # The oversized file can never be dispatched, so it must not be part
        # of count/total (the coverage denominator) -- it is reported apart.
        assert result["security"]["count"] == 1
        assert result["security"]["total"] == 1
        assert result["security"]["excluded"] == 1

    def test_dim_estimates_incremental_never_requeues_excluded(
        self, tmp_path: Path, api_provider,
    ):
        """The original symptom: with a warm cache for every dispatchable
        file, an incremental run must have NOTHING left to dispatch."""
        from quodeq.analysis.cache import CacheEntry, build_cache_key_for_file

        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])
        config.options.incremental = True
        cache = LocalFileBackend(root=tmp_path / "cache")
        key = build_cache_key_for_file(config, "small.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1, findings=[],
            files_read=1, file_path="small.py", dimension="security",
            model_id="test-model",
        ))

        with patch(
            "quodeq.analysis._dim_estimates.LocalFileBackend", return_value=cache,
        ):
            result = compute_dim_estimates(config, ["security"])

        assert result["security"]["count"] == 0
        assert result["security"]["cached"] == 1
        assert result["security"]["total"] == 1


class TestCoverageDenominator:
    def test_source_file_count_reflects_api_eligibility(
        self, tmp_path: Path, api_provider,
    ):
        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])

        assert config.source_file_count == 1

    def test_source_file_count_unchanged_for_cli_provider(
        self, tmp_path: Path, cli_provider,
    ):
        src = tmp_path / "src"
        _write_repo(src)
        config = _make_config(src, ["small.py", "big.py"])

        assert config.source_file_count == 2


class TestWorkerNeverDropsSilently:
    def _analysis_config(self, queue_path: Path, jsonl_file: Path):
        from quodeq.analysis._config import AnalysisConfig
        return AnalysisConfig(
            queue_path=queue_path, jsonl_file=jsonl_file,
            max_files_per_agent=10, agent_id="a1",
        )

    def test_gather_writes_skipped_marker_for_oversized_taken_file(
        self, tmp_path: Path, api_provider,
    ):
        from quodeq.analysis.subagents.file_queue import FileQueue
        from quodeq.analysis.subprocess import _gather_api_source_files

        src = tmp_path / "src"
        _write_repo(src)
        queue_path = tmp_path / "q.json"
        FileQueue(queue_path, ["small.py", "big.py"])
        jsonl_file = tmp_path / "security_evidence.jsonl"
        stream_file = tmp_path / "a1.stream"

        source_files = _gather_api_source_files(
            src, self._analysis_config(queue_path, jsonl_file), jsonl_file, stream_file,
        )

        assert source_files == [src / "small.py"]
        markers = [
            json.loads(line)
            for line in jsonl_file.read_text().splitlines()
            if json.loads(line).get("_marker") == "file_done"
        ]
        assert markers == [{
            "_marker": "file_done", "file": "big.py", "status": "skipped",
            "reason": markers[0]["reason"],
        }]
        assert "size" in markers[0]["reason"]

    def test_gather_writes_skipped_marker_even_when_nothing_dispatchable(
        self, tmp_path: Path, api_provider,
    ):
        from quodeq.analysis.subagents.file_queue import FileQueue
        from quodeq.analysis.subprocess import _gather_api_source_files

        src = tmp_path / "src"
        _write_repo(src)
        queue_path = tmp_path / "q.json"
        FileQueue(queue_path, ["big.py"])
        jsonl_file = tmp_path / "security_evidence.jsonl"
        stream_file = tmp_path / "a1.stream"

        source_files = _gather_api_source_files(
            src, self._analysis_config(queue_path, jsonl_file), jsonl_file, stream_file,
        )

        assert source_files is None
        content = jsonl_file.read_text()
        assert '"status": "skipped"' in content.replace('": "', '": "') or "skipped" in content


class TestSkippedMarkerSemantics:
    def test_router_accepts_skipped_status(self, tmp_path: Path):
        from quodeq.analysis.mcp.router import FindingsRouter

        out = tmp_path / "ev.jsonl"
        calls: list[tuple[str, list]] = []
        with out.open("w", encoding="utf-8") as fh:
            router = FindingsRouter(fh, on_file_done=lambda f, fs: calls.append((f, fs)))
            router.mark_file_done(file="big.py", status="skipped", reason="too large")

        entry = json.loads(out.read_text().strip())
        assert entry["status"] == "skipped"
        assert calls == []  # skipped must never write a cache entry

    def test_failure_streak_ignores_skipped_markers(self, tmp_path: Path):
        from quodeq.analysis.cache._failure_streak import FailureStreakWatcher

        jsonl = tmp_path / "ev.jsonl"
        lines = [
            json.dumps({"_marker": "file_done", "file": f"f{i}.py", "status": "skipped"})
            for i in range(50)
        ]
        jsonl.write_text("\n".join(lines) + "\n")

        watcher = FailureStreakWatcher(jsonl, threshold=3)
        offset, streak, recent = watcher._scan_once(0, 0, [])
        assert streak == 0
        assert recent == []


class TestSizeAwareBatching:
    """Raising the size cap must not overflow the context via multi-file
    batches: one model call's inlined file content stays within the prompt
    char budget, and an oversized file dispatches solo."""

    def _files(self, tmp_path: Path, sizes: list[int]) -> list[Path]:
        out = []
        for i, size in enumerate(sizes):
            p = tmp_path / f"f{i}.py"
            p.write_text("x" * size)
            out.append(p)
        return out

    def test_greedy_packing_preserves_order(self, tmp_path: Path):
        from quodeq.analysis.subprocess import _batch_files_by_size

        files = self._files(tmp_path, [100, 100, 100, 100])
        batches = _batch_files_by_size(files, budget=250)

        assert batches == [files[0:2], files[2:4]]

    def test_oversized_file_goes_solo(self, tmp_path: Path):
        from quodeq.analysis.subprocess import _batch_files_by_size

        files = self._files(tmp_path, [50, 900, 50])
        batches = _batch_files_by_size(files, budget=300)

        assert batches == [[files[0]], [files[1]], [files[2]]]

    def test_empty_input_yields_no_batches(self, tmp_path: Path):
        from quodeq.analysis.subprocess import _batch_files_by_size

        assert _batch_files_by_size([], budget=300) == []

    def test_bridge_makes_one_api_call_per_sub_batch(
        self, tmp_path: Path, api_provider, monkeypatch,
    ):
        from unittest.mock import patch as mpatch
        from quodeq.analysis._config import AnalysisConfig
        from quodeq.analysis.subagents.file_queue import FileQueue
        from quodeq.analysis.subprocess import _run_api_analysis_bridge

        src = tmp_path / "src"
        src.mkdir()
        for name in ("a.py", "b.py", "c.py"):
            (src / name).write_text("x = 1\n" * 20)  # 120 bytes each
        queue_path = tmp_path / "q.json"
        FileQueue(queue_path, ["a.py", "b.py", "c.py"])
        jsonl_file = tmp_path / "security_evidence.jsonl"
        cfg = AnalysisConfig(
            queue_path=queue_path, jsonl_file=jsonl_file,
            max_files_per_agent=10, agent_id="a1", dimension="security",
        )

        monkeypatch.setenv("QUODEQ_MAX_API_PROMPT_CHARS", "150")
        calls: list[list[str]] = []
        with mpatch(
            "quodeq.analysis.subprocess._resolve_provider_config",
            return_value=("m", "http://localhost:1", ""),
        ), mpatch(
            "quodeq.analysis._api_runner.run_api_analysis",
            side_effect=lambda **kw: calls.append(kw["source_file_paths"]),
        ):
            _run_api_analysis_bridge(src, "prompt", tmp_path / "a1.stream", cfg)

        # 120B each with a 150B budget: every file gets its own call.
        assert calls == [["a.py"], ["b.py"], ["c.py"]]


class TestEstimatesSidecarRoundTrip:
    def test_excluded_survives_write_read_round_trip(self, tmp_path: Path):
        from quodeq.shared.dim_estimates_io import read_dim_estimates, write_dim_estimates

        estimates = {"security": {
            "count": 3, "reason": "incremental", "total": 10, "cached": 7, "excluded": 2,
        }}
        write_dim_estimates(tmp_path, estimates)
        assert read_dim_estimates(tmp_path) == estimates

    def test_legacy_payload_defaults_excluded_to_zero(self, tmp_path: Path):
        from quodeq.shared.dim_estimates_io import (
            DIM_ESTIMATES_FILENAME, read_dim_estimates,
        )

        (tmp_path / DIM_ESTIMATES_FILENAME).write_text(
            json.dumps({"security": {"count": 5, "reason": "incremental"}})
        )
        loaded = read_dim_estimates(tmp_path)
        assert loaded["security"]["excluded"] == 0
