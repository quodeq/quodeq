from __future__ import annotations
import json
from pathlib import Path

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.cache.dimension_helpers import persist_dispatch_results


def _make_config(src: Path) -> RunConfig:
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=src, options=AnalysisOptions(subagent_model="m"),
    )


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(l) + "\n" for l in lines))


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


class TestPersistFiltersByOkMarker:
    def test_only_ok_files_persisted(self, tmp_path: Path, cache: LocalFileBackend):
        src = tmp_path / "src"; src.mkdir()
        for f in ("a.py", "b.py", "c.py"):
            (src / f).write_text("x")
        config = _make_config(src)
        jsonl = tmp_path / "dim_evidence.jsonl"
        _write_jsonl(jsonl, [
            {"file": "a.py", "req": "X-1", "t": "violation", "line": 1, "severity": "minor", "w": "w", "reason": "r"},
            {"_marker": "file_done", "file": "a.py", "status": "ok"},
            # b.py: no marker (worker crashed mid-file)
            # c.py: explicit error
            {"_marker": "file_done", "file": "c.py", "status": "error", "reason": "token_limit"},
        ])
        miss_keys = {f: f"key-{f}" for f in ("a.py", "b.py", "c.py")}
        persist_dispatch_results(
            config, "security", miss_files=["a.py", "b.py", "c.py"],
            jsonl_path=jsonl, miss_keys=miss_keys, cache=cache,
        )
        assert cache.get("key-a.py") is not None
        assert cache.get("key-b.py") is None
        assert cache.get("key-c.py") is None

    def test_clean_file_with_ok_marker_is_cached_empty(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        src = tmp_path / "src"; src.mkdir()
        (src / "clean.py").write_text("x")
        config = _make_config(src)
        jsonl = tmp_path / "dim_evidence.jsonl"
        _write_jsonl(jsonl, [
            {"_marker": "file_done", "file": "clean.py", "status": "ok"},
        ])
        persist_dispatch_results(
            config, "security", miss_files=["clean.py"],
            jsonl_path=jsonl, miss_keys={"clean.py": "key-clean"}, cache=cache,
        )
        entry = cache.get("key-clean")
        assert entry is not None
        assert entry.findings == []

    def test_orphan_findings_without_marker_not_cached(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        # Findings exist but no ok marker: worker wrote some findings then died.
        src = tmp_path / "src"; src.mkdir()
        (src / "x.py").write_text("x")
        config = _make_config(src)
        jsonl = tmp_path / "dim_evidence.jsonl"
        _write_jsonl(jsonl, [
            {"file": "x.py", "req": "X-1", "t": "violation", "line": 1, "severity": "minor", "w": "w", "reason": "r"},
        ])
        persist_dispatch_results(
            config, "security", miss_files=["x.py"],
            jsonl_path=jsonl, miss_keys={"x.py": "key-x"}, cache=cache,
        )
        assert cache.get("key-x") is None

    def test_missing_jsonl_writes_nothing(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        src = tmp_path / "src"; src.mkdir()
        config = _make_config(src)
        persist_dispatch_results(
            config, "security", miss_files=["a.py"],
            jsonl_path=tmp_path / "missing.jsonl",
            miss_keys={"a.py": "key-a"}, cache=cache,
        )
        assert cache.get("key-a") is None
