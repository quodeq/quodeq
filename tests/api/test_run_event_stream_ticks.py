"""Unit tests for the SSE run-event watcher: compute_tick and run_events_generator."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from quodeq.api._run_event_stream import (
    WatcherState,
    run_events_generator,
    compute_tick,
)
from tests.api._run_event_stream_helpers import (
    _write_dim_eval,
    _write_finding_event,
    _write_status,
)


# --- compute_tick tests ---

def test_compute_tick_initial_emits_status_when_status_json_present(tmp_path: Path):
    _write_status(tmp_path, "running")
    state = WatcherState()
    events, new_state = compute_tick(tmp_path, state)
    types = [e[0] for e in events]
    assert "status" in types


def test_compute_tick_emits_status_pending_when_status_json_missing(tmp_path: Path):
    state = WatcherState()
    events, new_state = compute_tick(tmp_path, state)
    status_events = [e for e in events if e[0] == "status"]
    assert len(status_events) == 1
    payload = json.loads(status_events[0][1])
    assert payload["state"] == "pending"


def test_compute_tick_does_not_re_emit_unchanged_status(tmp_path: Path):
    _write_status(tmp_path)
    state = WatcherState()
    _, state2 = compute_tick(tmp_path, state)
    events, _ = compute_tick(tmp_path, state2)
    status_events = [e for e in events if e[0] == "status"]
    assert status_events == []


def test_compute_tick_re_emits_status_when_mtime_changes(tmp_path: Path):
    import os
    import time as _time
    _write_status(tmp_path, "running")
    state = WatcherState()
    _, state2 = compute_tick(tmp_path, state)
    _time.sleep(0.05)
    os.utime(tmp_path / "status.json", None)
    events, _ = compute_tick(tmp_path, state2)
    status_events = [e for e in events if e[0] == "status"]
    assert len(status_events) == 1


def test_compute_tick_emits_dimension_events_for_new_files(tmp_path: Path):
    _write_status(tmp_path)
    _write_dim_eval(tmp_path, "timeliness")
    state = WatcherState()
    events, new_state = compute_tick(tmp_path, state)
    dim_events = [e for e in events if e[0] == "dimension-completed"]
    assert len(dim_events) == 1
    assert "timeliness" in new_state.emitted_dimensions


def test_compute_tick_does_not_re_emit_already_emitted_dimensions(tmp_path: Path):
    _write_status(tmp_path)
    _write_dim_eval(tmp_path, "timeliness")
    state = WatcherState()
    _, state2 = compute_tick(tmp_path, state)
    events, _ = compute_tick(tmp_path, state2)
    dim_events = [e for e in events if e[0] == "dimension-completed"]
    assert dim_events == []


def test_compute_tick_emits_findings_advances_counter(tmp_path: Path):
    _write_status(tmp_path)
    _write_finding_event(tmp_path, "P1", line=1)
    _write_finding_event(tmp_path, "P2", line=2)
    state = WatcherState()
    events, new_state = compute_tick(tmp_path, state)
    finding_events = [e for e in events if e[0] == "finding"]
    assert len(finding_events) == 2
    assert new_state.last_event_counter == 2


def test_compute_tick_skips_findings_already_emitted(tmp_path: Path):
    _write_status(tmp_path)
    _write_finding_event(tmp_path, "P1", line=1)
    _write_finding_event(tmp_path, "P2", line=2)
    # First tick to consume first finding and record its timestamp
    state = WatcherState()
    _, state_after_first = compute_tick(tmp_path, state)
    # Only P1 emitted — advance to just past P1's timestamp
    assert state_after_first.last_event_counter == 2  # both are in the same tick
    # Tick again: nothing new
    events, _ = compute_tick(tmp_path, state_after_first)
    finding_events = [e for e in events if e[0] == "finding"]
    assert finding_events == []


def test_compute_tick_handles_missing_events_jsonl(tmp_path: Path):
    _write_status(tmp_path)
    state = WatcherState()
    events, _ = compute_tick(tmp_path, state)
    finding_events = [e for e in events if e[0] == "finding"]
    assert finding_events == []


def test_compute_tick_never_crashes_on_a_read_or_shaping_failure(tmp_path: Path, monkeypatch, caplog):
    """Read and shaping failures both degrade to "no findings this tick"
    instead of crashing compute_tick -- one guard covers both."""
    _write_status(tmp_path)
    _write_finding_event(tmp_path, "P1", line=1)

    def _boom(*a, **k):
        raise AttributeError("'NoneType' object has no attribute 'practice_id'")
    targets = ("quodeq.api._run_event_watcher.payload_as_sse_finding",
               "quodeq.api._run_event_watcher.read_new_findings_from_events")
    for target in targets:
        with monkeypatch.context() as m:
            m.setattr(target, _boom)
            state = WatcherState(); caplog.clear()
            with caplog.at_level("WARNING"):
                events, new_state = compute_tick(tmp_path, state)
        assert [e for e in events if e[0] == "finding"] == []
        assert new_state.last_event_counter == state.last_event_counter
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1, [(r.name, r.message) for r in warnings]
        assert warnings[0].message.startswith(f"events.jsonl read failed for {tmp_path}: ")


def test_compute_tick_handles_malformed_status_json(tmp_path: Path):
    (tmp_path / "status.json").write_text("not valid json {")
    state = WatcherState()
    events, _ = compute_tick(tmp_path, state)
    status_events = [e for e in events if e[0] == "status"]
    assert len(status_events) == 1


def test_compute_tick_logs_exactly_once_on_corrupt_status_json(tmp_path: Path, caplog):
    """Log parity with the pre-move inline reader: a corrupt status.json
    produces exactly one WARNING total (across every logger, not just
    api._run_event_watcher's own), with the "status.json read failed
    at ...: ..." message -- not the two records a naive delegation to
    wiring.read_status/read_run_status_json would produce (one logged
    inside run_status_store, one logged again by this caller). Nothing
    else in this minimal fixture (no evaluation dir, no events.jsonl) can
    log, so any record beyond the one this reader emits is the regression
    a fix-round review caught."""
    (tmp_path / "status.json").write_text("not valid json {")
    state = WatcherState()
    with caplog.at_level("WARNING"):
        compute_tick(tmp_path, state)
    assert len(caplog.records) == 1, [(r.name, r.message) for r in caplog.records]
    record = caplog.records[0]
    assert record.name == "quodeq.api._run_event_watcher"
    assert record.levelname == "WARNING"
    assert record.message.startswith("status.json read failed at ")
    assert "status.json" in record.message


def test_compute_tick_logs_nothing_on_non_dict_status_json(tmp_path: Path, caplog):
    """Valid JSON that isn't a dict (e.g. a bare list) is not an error --
    it silently becomes the pending status, exactly like the pre-move
    inline reader, with no WARNING at all (not even from a lower-level
    reader that would treat it as corrupt)."""
    (tmp_path / "status.json").write_text("[1, 2, 3]")
    state = WatcherState()
    with caplog.at_level("WARNING"):
        events, _ = compute_tick(tmp_path, state)
    assert caplog.records == [], [(r.name, r.message) for r in caplog.records]
    status_events = [e for e in events if e[0] == "status"]
    assert len(status_events) == 1
    payload = json.loads(status_events[0][1])
    assert payload["state"] == "pending"


# --- run_events_generator tests ---

def _drain_generator(gen, max_frames: int) -> list[str]:
    out = []
    for frame in gen:
        if frame.startswith(":"):
            continue
        out.append(frame)
        if len(out) >= max_frames:
            break
    return out


def test_run_events_generator_emits_status_then_done_for_terminal_run(tmp_path: Path):
    _write_status(tmp_path, state="done")
    frames = list(run_events_generator(tmp_path, last_event_ts=None, tick_seconds=0.0))
    non_keepalive = [f for f in frames if not f.startswith(":")]
    assert any("event: status" in f for f in non_keepalive)
    assert any("event: done" in f for f in non_keepalive)


def test_run_events_generator_emits_finding_with_event_id(tmp_path: Path):
    _write_status(tmp_path, state="running")
    _write_finding_event(tmp_path)
    gen = run_events_generator(tmp_path, last_event_ts=None, tick_seconds=0.0)
    frames = _drain_generator(gen, max_frames=3)
    finding_frames = [f for f in frames if "event: finding" in f]
    assert len(finding_frames) == 1
    # event_id is an ISO timestamp string
    assert "id: " in finding_frames[0]
    # payload id is counter = 1
    data = json.loads(next(l for l in finding_frames[0].splitlines() if l.startswith("data: "))[6:])
    assert data["id"] == 1


def test_run_events_generator_respects_initial_last_event_ts(tmp_path: Path):
    _write_status(tmp_path, state="running")
    _write_finding_event(tmp_path, p="P1", line=1)
    _write_finding_event(tmp_path, p="P2", line=2)

    # First, drain all findings to get the timestamp of the first one
    state = WatcherState()
    events, state1 = compute_tick(tmp_path, state)
    finding_events = [e for e in events if e[0] == "finding"]
    assert len(finding_events) == 2
    # The ISO timestamp of the first finding is its event_id (third element)
    first_ts_str = finding_events[0][2]
    first_ts = datetime.fromisoformat(first_ts_str)

    # Start generator from after first finding's timestamp
    gen = run_events_generator(tmp_path, last_event_ts=first_ts, tick_seconds=0.0)
    frames = _drain_generator(gen, max_frames=3)
    finding_frames = [f for f in frames if "event: finding" in f]
    assert len(finding_frames) == 1
    data = json.loads(next(l for l in finding_frames[0].splitlines() if l.startswith("data: "))[6:])
    assert data["practice_id"] == "P2"


def test_run_events_generator_handles_already_terminal_run(tmp_path: Path):
    _write_status(tmp_path, state="failed")
    _write_finding_event(tmp_path)
    frames = list(run_events_generator(tmp_path, last_event_ts=None, tick_seconds=0.0))
    non_keepalive = [f for f in frames if not f.startswith(":")]
    assert any("event: status" in f for f in non_keepalive)
    assert any("event: finding" in f for f in non_keepalive)
    assert any("event: done" in f for f in non_keepalive)


# Grade updates intentionally do NOT flow through SSE anymore -- see
# WatcherState's docstring in _run_event_watcher.py. compute_tick only
# emits lifecycle events (status, dimension-completed, finding, done) for
# in-progress evals; routes_findings.py returns the rescored payload
# synchronously on mutation instead.

# Wire-characterization: exact SSE frame sequence, byte for byte -- pins
# the frame text so moving readers between api/_run_event_watcher.py and
# services/run_event_readers.py can't change what goes over the wire.

def test_finished_run_sse_sequence_is_byte_identical(tmp_path: Path):
    """A run with one dimension, one finding, and a terminal status emits
    exactly: status, dimension-completed, finding, done -- in that order,
    with the exact SSE frame text (not just "some frame of this type")."""
    _write_status(tmp_path, state="done")
    _write_dim_eval(tmp_path, "timeliness", score=90)
    _write_finding_event(tmp_path, p="P1", line=1)

    frames = list(run_events_generator(tmp_path, last_event_ts=None, tick_seconds=0.0))
    non_keepalive = [f for f in frames if not f.startswith(":")]

    assert len(non_keepalive) == 4, non_keepalive
    status_frame, dim_frame, finding_frame, done_frame = non_keepalive

    assert status_frame == (
        'event: status\ndata: {"state":"done"}\n\n'
    )
    assert dim_frame == (
        'event: dimension-completed\n'
        'data: {"dimension":"timeliness","score":90}\n\n'
    )
    assert finding_frame.startswith('id: ')
    assert '\nevent: finding\n' in finding_frame
    assert finding_frame.endswith(
        'data: {"id":1,"practice_id":"P1","dimension":"dim","requirement":null,'
        '"verdict":"violation","severity":"medium","file":"x.py","line":1,'
        '"end_line":null,"title":"t","reason":"r","snippet":"s","confidence":100,'
        '"provenance_downgrade":false,"scope_downgrade":null,"carried_forward":false}\n\n'
    )
    assert done_frame == 'event: done\ndata: {"state":"done"}\n\n'


def test_pending_run_emits_only_status_pending_when_status_json_absent(tmp_path: Path):
    """No status.json yet: exactly one status frame reporting `pending`,
    nothing else -- the watcher's read-failure/absence defaults stay
    byte-identical across the reader move."""
    frames = list(run_events_generator(tmp_path, last_event_ts=None, tick_seconds=0.0))
    non_keepalive = [f for f in frames if not f.startswith(":")]
    assert non_keepalive == ['event: status\ndata: {"state":"pending"}\n\n']
