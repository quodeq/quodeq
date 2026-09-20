"""API file-size cap at dispatch time: skipped markers, size-aware batching, estimates sidecar."""
from __future__ import annotations

import json
from pathlib import Path

from ._api_size_cap_dispatch_helpers import _write_repo


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
        from quodeq.analysis.cache.failure_streak import FailureStreakWatcher

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
        self, tmp_path: Path, api_provider,
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

        calls: list[list[str]] = []
        with mpatch(
            "quodeq.analysis.subprocess._resolve_provider_config",
            return_value=("m", "http://localhost:1", ""),
        ), mpatch(
            "quodeq.analysis._api_runner.run_api_analysis",
            side_effect=lambda **kw: calls.append(kw["request"].source_file_paths),
        ):
            # The budget is injected, not exported: the bridge's ``env``
            # mapping IS the environment it sees, so an empty one would mean
            # "nothing set" rather than "fall back to the process".
            _run_api_analysis_bridge(
                src, "prompt", tmp_path / "a1.stream", cfg,
                {"QUODEQ_MAX_API_PROMPT_CHARS": "150"},
            )

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
