"""Incremental dispatch-JSONL reader (``DispatchJsonlState``).

The periodic-persist watcher used to re-read and re-parse the whole
evidence JSONL on every tick, so persist cost grew with elapsed dispatch
time. These tests pin the incremental contract: consume only appended
complete lines, leave a torn trailing line for the writer, fall back to a
full re-read when the file was truncated or rewritten in place, and let
``persist_dispatch_results`` skip files nothing touched since the last tick.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.cache._jsonl_state import DispatchJsonlState
from quodeq.analysis.cache._persist_watcher import CachePersistProvenance, CachePersistTarget
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    _group_findings_by_file,
    persist_dispatch_results,
)


def _line(obj: dict) -> str:
    return json.dumps(obj) + "\n"


def _finding(f: str, line: int) -> dict:
    return {"file": f, "req": "X-1", "t": "violation", "line": line, "w": "w"}


def _ok(f: str) -> dict:
    return {"_marker": "file_done", "file": f, "status": "ok"}


def _append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(text)


class TestAdvance:
    def test_second_advance_consumes_only_appended_lines(self, tmp_path: Path):
        jsonl = tmp_path / "e.jsonl"
        jsonl.write_text(_line(_finding("a.py", 1)) + _line(_ok("a.py")))
        state = DispatchJsonlState()
        state.advance(jsonl)
        first_offset = state.offset
        assert state.ok_files() == {"a.py"}
        assert len(state.grouped["a.py"]) == 1

        _append(jsonl, _line(_finding("b.py", 2)) + _line(_ok("b.py")))
        state.advance(jsonl)
        assert state.offset == jsonl.stat().st_size > first_offset
        assert state.ok_files() == {"a.py", "b.py"}
        # a.py was not re-ingested: still exactly one finding.
        assert len(state.grouped["a.py"]) == 1

    def test_partial_trailing_line_waits_for_newline(self, tmp_path: Path):
        jsonl = tmp_path / "e.jsonl"
        complete = _line(_finding("a.py", 1))
        marker = json.dumps(_ok("a.py"))
        jsonl.write_text(complete + marker[:-3])  # writer mid-line
        state = DispatchJsonlState()
        state.advance(jsonl)
        # Expect the offset the file actually has, not len(complete.encode()):
        # write_text emits CRLF on Windows, and the state counts on-disk bytes.
        assert state.offset == jsonl.read_bytes().index(b"\n") + 1
        assert state.ok_files() == set()

        _append(jsonl, marker[-3:] + "\n")
        state.advance(jsonl)
        assert state.ok_files() == {"a.py"}
        assert state.offset == jsonl.stat().st_size

    def test_crlf_lines_are_consumed_and_parsed(self, tmp_path: Path):
        # Windows text-mode writers end lines with CRLF. The offset must land
        # after the LF, and the CR must not leak into the parsed entries.
        jsonl = tmp_path / "e.jsonl"
        body = (_line(_finding("a.py", 1)) + _line(_ok("a.py"))).replace("\n", "\r\n")
        jsonl.write_bytes(body.encode() + b'{"file": "b.py"')  # torn tail
        state = DispatchJsonlState()
        state.advance(jsonl)
        assert state.offset == len(body.encode())
        assert state.ok_files() == {"a.py"}
        assert [e["line"] for e in state.grouped["a.py"]] == [1]

    def test_include_tail_reads_a_line_without_newline(self, tmp_path: Path):
        jsonl = tmp_path / "e.jsonl"
        jsonl.write_text(_line(_finding("a.py", 1)) + json.dumps(_ok("a.py")))
        state = DispatchJsonlState()
        state.advance(jsonl, include_tail=True)
        assert state.ok_files() == {"a.py"}
        assert state.offset == jsonl.stat().st_size

    def test_truncation_resets_and_rereads(self, tmp_path: Path):
        jsonl = tmp_path / "e.jsonl"
        jsonl.write_text(
            "".join(_line(_finding("a.py", i)) for i in range(5)) + _line(_ok("a.py"))
        )
        state = DispatchJsonlState()
        state.advance(jsonl)
        assert len(state.grouped["a.py"]) == 5

        jsonl.write_text(_line(_finding("b.py", 1)) + _line(_ok("b.py")))
        state.advance(jsonl)
        assert state.ok_files() == {"b.py"}
        assert "a.py" not in state.grouped
        assert state.offset == jsonl.stat().st_size

    def test_in_place_dedup_rewrite_that_keeps_size_is_detected(self, tmp_path: Path):
        """The pool's deduplicate_jsonl drops lines before the offset while a
        longer tail keeps the file at least as large as before. A size check
        alone would seek into the middle of a line; the state must instead
        re-read and end up identical to a fresh one-shot read."""
        jsonl = tmp_path / "e.jsonl"
        dup = _finding("a.py", 1)
        jsonl.write_text(_line(dup) + _line(dup) + _line(_ok("a.py")))
        state = DispatchJsonlState()
        state.advance(jsonl)
        assert len(state.grouped["a.py"]) == 2

        long_tail = {**_finding("b.py", 2), "reason": "x" * 200}
        jsonl.write_text(
            _line(dup) + _line(_ok("a.py")) + _line(long_tail) + _line(_ok("b.py"))
        )
        assert jsonl.stat().st_size >= state.offset
        state.advance(jsonl)
        expected_grouped, expected_ok = _group_findings_by_file(jsonl)
        assert state.grouped == expected_grouped
        assert state.ok_files() == expected_ok
        assert state.dirty == {"a.py", "b.py"}

    def test_missing_file_reads_as_empty(self, tmp_path: Path):
        state = DispatchJsonlState()
        state.advance(tmp_path / "missing.jsonl")
        assert state.grouped == {}
        assert state.ok_files() == set()
        assert state.offset == 0

    def test_malformed_and_non_object_lines_are_skipped(self, tmp_path: Path):
        jsonl = tmp_path / "e.jsonl"
        jsonl.write_bytes(
            b'{"file": "a.py", "t"\n[1, 2]\n\xff\xfe\n' + _line(_ok("a.py")).encode()
        )
        state = DispatchJsonlState()
        state.advance(jsonl)
        assert state.grouped == {}
        assert state.ok_files() == {"a.py"}

    def test_dirty_tracks_files_touched_since_last_clear(self, tmp_path: Path):
        jsonl = tmp_path / "e.jsonl"
        jsonl.write_text(_line(_finding("a.py", 1)) + _line(_ok("a.py")))
        state = DispatchJsonlState()
        state.advance(jsonl)
        assert state.dirty == {"a.py"}

        state.dirty.clear()
        state.advance(jsonl)  # nothing appended
        assert state.dirty == set()

        _append(jsonl, _line(_ok("b.py")))
        state.advance(jsonl)
        assert state.dirty == {"b.py"}


# ------------------------------------------------------------------
# persist_dispatch_results with a shared state
# ------------------------------------------------------------------


class _RecordingCache:
    """LocalFileBackend wrapper that records put keys and can fail one put."""

    def __init__(self, inner: LocalFileBackend) -> None:
        self._inner = inner
        self.puts: list[str] = []
        self.fail_next_put = False

    def put(self, key, entry) -> None:
        if self.fail_next_put:
            self.fail_next_put = False
            raise OSError("disk full")
        self.puts.append(key)
        self._inner.put(key, entry)

    def get(self, key):
        return self._inner.get(key)

    def has(self, key) -> bool:
        return self._inner.has(key)

    def delete(self, key) -> None:
        self._inner.delete(key)

    def stats(self):
        return self._inner.stats()


def _make_config(src: Path) -> RunConfig:
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=src, options=AnalysisOptions(subagent_model="m"),
    )


def _persist(config: RunConfig, jsonl: Path, cache, files: list[str], state=None) -> None:
    persist_dispatch_results(
        config, "security",
        classify=ClassifyResult(
            misses=files, miss_keys={f: "key-" + f.replace(".", "-") for f in files},
        ),
        provenance=CachePersistProvenance(
            standards_hash="", params_hash="", effective_params={}, prompts_hash="",
        ),
        target=CachePersistTarget(jsonl_path=jsonl, cache=cache, state=state),
    )


@pytest.fixture
def scenario(tmp_path: Path) -> tuple[RunConfig, Path, _RecordingCache]:
    src = tmp_path / "src"
    src.mkdir()
    for f in ("a.py", "b.py"):
        (src / f).write_text("x")
    jsonl = tmp_path / "security_evidence.jsonl"
    jsonl.write_text(_line(_finding("a.py", 1)) + _line(_ok("a.py")))
    return _make_config(src), jsonl, _RecordingCache(LocalFileBackend(root=tmp_path / "cache"))


class TestPersistWithState:
    def test_unchanged_ok_file_is_not_re_put_on_later_ticks(self, scenario):
        config, jsonl, cache = scenario
        state = DispatchJsonlState()
        _persist(config, jsonl, cache, ["a.py", "b.py"], state)
        assert cache.puts == ["key-a-py"]

        _persist(config, jsonl, cache, ["a.py", "b.py"], state)  # nothing appended
        assert cache.puts == ["key-a-py"]

        _append(jsonl, _line(_ok("b.py")))
        _persist(config, jsonl, cache, ["a.py", "b.py"], state)
        assert cache.puts == ["key-a-py", "key-b-py"]
        assert cache.get("key-b-py").findings == []

    def test_new_finding_for_persisted_file_triggers_re_put(self, scenario):
        config, jsonl, cache = scenario
        state = DispatchJsonlState()
        _persist(config, jsonl, cache, ["a.py"], state)

        _append(jsonl, _line(_finding("a.py", 7)) + _line(_ok("a.py")))
        _persist(config, jsonl, cache, ["a.py"], state)
        assert cache.puts == ["key-a-py", "key-a-py"]
        assert len(cache.get("key-a-py").findings) == 2

    def test_failed_put_keeps_file_dirty_for_next_tick(self, scenario):
        config, jsonl, cache = scenario
        state = DispatchJsonlState()
        cache.fail_next_put = True
        with pytest.raises(OSError):
            _persist(config, jsonl, cache, ["a.py"], state)
        assert cache.puts == []

        _persist(config, jsonl, cache, ["a.py"], state)
        assert cache.puts == ["key-a-py"]

    def test_without_state_every_call_persists_everything(self, scenario):
        config, jsonl, cache = scenario
        _persist(config, jsonl, cache, ["a.py"])
        _persist(config, jsonl, cache, ["a.py"])
        assert cache.puts == ["key-a-py", "key-a-py"]
