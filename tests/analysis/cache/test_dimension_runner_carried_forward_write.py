"""Cache replays must be distinguishable from this scan's own findings.

Split from test_dimension_runner_carried_forward.py: the direct unit
tests for ``_write_findings`` / ``_emit_cached_findings`` (the write
side). The integration tests that drive replay through
``process_dimension_with_cache`` live in
test_dimension_runner_carried_forward_replay.py.

The live evaluation feed filters on carried_forward. It is stamped here,
at the only place that knows a finding came from the cache rather than
from the running scan.
"""
import json
from pathlib import Path

from quodeq.analysis.cache.dimension_runner import (
    _emit_cached_findings,
    _write_findings,
)


def _finding(title: str) -> dict:
    return {
        "file": "a.py", "line": 1, "t": "violation", "w": title,
        "p": "P1", "d": "security", "req": "X-1", "severity": "minor",
        "snippet": "x", "reason": "r",
    }


def test_write_findings_stamps_carried_forward(tmp_path: Path):
    jsonl = tmp_path / "security_evidence.jsonl"
    _write_findings(jsonl, [_finding("carry-a")], append=False, emit_events=False)
    written = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert written[0]["carried_forward"] is True


def test_emit_cached_findings_uses_injected_writer_factory(tmp_path: Path):
    """[8]: the event-log writer is an injectable seam. A fake factory
    receives the events.jsonl path and its emit() sees one JUDGMENT_CREATED
    event per replayed finding — no concrete EventLogWriter constructed."""
    class _RecordingWriter:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.events = []

        def emit(self, event) -> None:
            self.events.append(event)

    writers: list[_RecordingWriter] = []

    def factory(path: Path) -> _RecordingWriter:
        writer = _RecordingWriter(path)
        writers.append(writer)
        return writer

    events_log = tmp_path / "events.jsonl"
    _emit_cached_findings(
        events_log, [_finding("carry-a"), _finding("carry-b")],
        writer_factory=factory,
    )

    assert len(writers) == 1
    assert writers[0].path == events_log
    assert len(writers[0].events) == 2
    assert all(e.payload.title in {"carry-a", "carry-b"} for e in writers[0].events)


def test_write_findings_does_not_mutate_the_source_dicts(tmp_path: Path):
    """The dicts belong to the cache entry. Stamping in place risks the
    persist watcher writing the flag back into the cache, which would make
    a later fresh scan of the same file look carried."""
    jsonl = tmp_path / "security_evidence.jsonl"
    source = [_finding("carry-a")]
    _write_findings(jsonl, source, append=False, emit_events=False)
    assert "carried_forward" not in source[0]


def test_write_findings_does_not_stamp_unconsolidated_replays(tmp_path: Path):
    """A finding produced by a run that never completed was never consolidated
    into an Overview. Replaying it must read as this scan's own finding."""
    jsonl = tmp_path / "security_evidence.jsonl"
    _write_findings(
        jsonl, [_finding("carry-a")], append=False, emit_events=False,
        unconsolidated=[dict(_finding("pending-b"), file="b.py")],
    )
    written = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    by_title = {ln["w"]: ln for ln in written}
    assert by_title["carry-a"]["carried_forward"] is True
    assert "carried_forward" not in by_title["pending-b"]


def test_write_findings_orders_consolidated_replays_first(tmp_path: Path):
    """Foundation-then-new ordering in the JSONL, matching the existing
    carried-before-fresh contract."""
    jsonl = tmp_path / "security_evidence.jsonl"
    _write_findings(
        jsonl, [_finding("carry-a")], append=False, emit_events=False,
        unconsolidated=[dict(_finding("pending-b"), file="b.py")],
    )
    written = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert [ln["w"] for ln in written] == ["carry-a", "pending-b"]


def test_write_findings_does_not_stamp_the_unconsolidated_source_dicts(tmp_path: Path):
    jsonl = tmp_path / "security_evidence.jsonl"
    source = [dict(_finding("pending-b"), file="b.py")]
    _write_findings(
        jsonl, [], append=False, emit_events=False, unconsolidated=source,
    )
    assert "carried_forward" not in source[0]


def test_write_findings_accepts_only_unconsolidated(tmp_path: Path):
    """A dimension whose every hit is unconsolidated still writes findings."""
    jsonl = tmp_path / "security_evidence.jsonl"
    _write_findings(
        jsonl, [], append=False, emit_events=False,
        unconsolidated=[dict(_finding("pending-b"), file="b.py")],
    )
    written = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert [ln["w"] for ln in written] == ["pending-b"]
