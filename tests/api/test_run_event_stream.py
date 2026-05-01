"""Unit tests for the SSE run-event watcher and serializers."""
from __future__ import annotations

import json

from quodeq.api._run_event_stream import (
    serialize_status_event,
    serialize_dimension_event,
    serialize_finding_event,
)


def test_serialize_status_event_returns_json_payload():
    status = {"state": "running", "phase": "analyzing", "current_dimension": "timeliness"}
    payload = serialize_status_event(status)
    assert json.loads(payload) == status


def test_serialize_status_event_with_missing_keys():
    payload = serialize_status_event({"state": "pending"})
    assert json.loads(payload) == {"state": "pending"}


def test_serialize_dimension_event_with_eval_data():
    payload = serialize_dimension_event(
        dimension="security",
        eval_data={"dimension": "security", "score": 92, "grade": "A"},
    )
    parsed = json.loads(payload)
    assert parsed["dimension"] == "security"
    assert parsed["score"] == 92
    assert parsed["grade"] == "A"


def test_serialize_dimension_event_without_eval_data():
    payload = serialize_dimension_event(dimension="security", eval_data=None)
    parsed = json.loads(payload)
    assert parsed == {"dimension": "security"}


def test_serialize_finding_event_includes_judgment_fields():
    judgment_dict = {
        "id": 42,
        "practice_id": "P-TIM-1",
        "dimension": "timeliness",
        "verdict": "violation",
        "severity": "high",
        "file": "src/x.py",
        "line": 10,
        "title": "Late finalize",
        "reason": "missed deadline",
    }
    payload = serialize_finding_event(judgment_dict)
    parsed = json.loads(payload)
    assert parsed["id"] == 42
    assert parsed["practice_id"] == "P-TIM-1"
    assert parsed["verdict"] == "violation"


from quodeq.api._run_event_stream import WatcherState


def test_watcher_state_initial_defaults():
    state = WatcherState()
    assert state.last_event_id == 0
    assert state.last_status_mtime is None
    assert state.emitted_dimensions == frozenset()


def test_watcher_state_with_initial_last_event_id():
    state = WatcherState(last_event_id=42)
    assert state.last_event_id == 42


def test_watcher_state_with_emitted_dimensions():
    state = WatcherState(emitted_dimensions=frozenset({"security", "timeliness"}))
    assert "security" in state.emitted_dimensions
    assert "timeliness" in state.emitted_dimensions


import json as _json
from pathlib import Path

from quodeq.api._run_event_stream import compute_tick
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def _write_status(run_dir: Path, state: str = "running") -> None:
    (run_dir / "status.json").write_text(_json.dumps({"state": state}))


def _write_dim_eval(run_dir: Path, dim: str, score: int = 90) -> None:
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(exist_ok=True)
    (eval_dir / f"{dim}.json").write_text(
        _json.dumps({"dimension": dim, "score": score}),
    )


def _insert_finding(run_dir: Path, p: str = "P1", line: int = 1) -> None:
    repo = SqliteFindingsRepository(run_dir)
    repo.insert_finding({
        "p": p, "file": "x.py", "line": line, "t": "violation",
        "severity": "medium", "d": "dim", "reason": "r", "snippet": "s", "w": "t",
    })


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
    payload = _json.loads(status_events[0][1])
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
    os.utime(tmp_path / "status.json", None)  # bump mtime
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


def test_compute_tick_emits_findings_with_id_advances_last_event_id(tmp_path: Path):
    _write_status(tmp_path)
    _insert_finding(tmp_path, "P1", line=1)
    _insert_finding(tmp_path, "P2", line=2)
    state = WatcherState()
    events, new_state = compute_tick(tmp_path, state)
    finding_events = [e for e in events if e[0] == "finding"]
    assert len(finding_events) == 2
    assert new_state.last_event_id == 2  # SQLite IDs are 1, 2


def test_compute_tick_skips_findings_already_emitted(tmp_path: Path):
    _write_status(tmp_path)
    _insert_finding(tmp_path, "P1", line=1)
    _insert_finding(tmp_path, "P2", line=2)
    state = WatcherState(last_event_id=1)
    events, new_state = compute_tick(tmp_path, state)
    finding_events = [e for e in events if e[0] == "finding"]
    assert len(finding_events) == 1
    assert new_state.last_event_id == 2


def test_compute_tick_handles_missing_evaluation_db(tmp_path: Path):
    _write_status(tmp_path)
    state = WatcherState()
    events, _ = compute_tick(tmp_path, state)
    # Should not crash and should not emit any finding events.
    finding_events = [e for e in events if e[0] == "finding"]
    assert finding_events == []


def test_compute_tick_handles_malformed_status_json(tmp_path: Path):
    (tmp_path / "status.json").write_text("not valid json {")
    state = WatcherState()
    events, _ = compute_tick(tmp_path, state)
    # Should not crash; emits a fallback status with state=pending.
    status_events = [e for e in events if e[0] == "status"]
    assert len(status_events) == 1


def _drain_generator(gen, max_frames: int) -> list[str]:
    """Pull at most max_frames from a generator, ignoring keepalives."""
    out = []
    for frame in gen:
        if frame.startswith(":"):
            continue
        out.append(frame)
        if len(out) >= max_frames:
            break
    return out


def test_run_events_generator_emits_status_then_done_for_terminal_run(tmp_path: Path):
    from quodeq.api._run_event_stream import run_events_generator

    _write_status(tmp_path, state="done")
    frames = list(run_events_generator(tmp_path, last_event_id=0, tick_seconds=0.0))
    # Should produce: status frame, then done frame, then return.
    non_keepalive = [f for f in frames if not f.startswith(":")]
    assert any("event: status" in f for f in non_keepalive)
    assert any("event: done" in f for f in non_keepalive)


def test_run_events_generator_emits_finding_with_event_id(tmp_path: Path):
    from quodeq.api._run_event_stream import run_events_generator

    _write_status(tmp_path, state="running")
    _insert_finding(tmp_path)
    gen = run_events_generator(tmp_path, last_event_id=0, tick_seconds=0.0)
    frames = _drain_generator(gen, max_frames=3)
    finding_frames = [f for f in frames if "event: finding" in f]
    assert len(finding_frames) == 1
    assert "id: 1" in finding_frames[0]


def test_run_events_generator_respects_initial_last_event_id(tmp_path: Path):
    from quodeq.api._run_event_stream import run_events_generator

    _write_status(tmp_path, state="running")
    _insert_finding(tmp_path, p="P1", line=1)
    _insert_finding(tmp_path, p="P2", line=2)
    gen = run_events_generator(tmp_path, last_event_id=1, tick_seconds=0.0)
    frames = _drain_generator(gen, max_frames=3)
    finding_frames = [f for f in frames if "event: finding" in f]
    assert len(finding_frames) == 1
    assert "id: 2" in finding_frames[0]


def test_run_events_generator_handles_already_terminal_run(tmp_path: Path):
    from quodeq.api._run_event_stream import run_events_generator

    _write_status(tmp_path, state="failed")
    _insert_finding(tmp_path)
    frames = list(run_events_generator(tmp_path, last_event_id=0, tick_seconds=0.0))
    non_keepalive = [f for f in frames if not f.startswith(":")]
    # Snapshot includes status, finding, then done.
    assert any("event: status" in f for f in non_keepalive)
    assert any("event: finding" in f for f in non_keepalive)
    assert any("event: done" in f for f in non_keepalive)
    # Generator terminates (we got the full list).
    assert non_keepalive[-1].startswith("id: ") or "event: done" in non_keepalive[-1]


def test_run_events_generator_emits_heartbeat_when_quiet(tmp_path: Path):
    """When no events fire for heartbeat_seconds, emit a :keepalive comment."""
    import time as _time
    from quodeq.api._run_event_stream import run_events_generator

    _write_status(tmp_path, state="running")
    gen = run_events_generator(
        tmp_path,
        last_event_id=0,
        tick_seconds=0.001,
        heartbeat_seconds=0.0,  # always due — every quiet tick should emit one
    )

    # Collect a small batch: initial keepalive + status frame + at least one
    # additional :keepalive (because the next tick has no new events).
    frames: list[str] = []
    deadline = _time.monotonic() + 1.0
    for frame in gen:
        frames.append(frame)
        if frames.count(":keepalive\n\n") >= 2:
            break
        if _time.monotonic() > deadline:
            break  # safety guard so the test never hangs

    keepalives = [f for f in frames if f == ":keepalive\n\n"]
    assert len(keepalives) >= 2, f"expected >=2 keepalives, got: {frames!r}"
