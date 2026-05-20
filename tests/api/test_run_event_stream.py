"""Unit tests for the SSE run-event watcher and serializers."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from quodeq.api._run_event_stream import (
    WatcherState,
    compute_tick,
    serialize_status_event,
    serialize_dimension_event,
    serialize_finding_event,
)
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter


# ---------------------------------------------------------------------------
# Serializer tests (unchanged behavior)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# WatcherState tests
# ---------------------------------------------------------------------------

def test_watcher_state_initial_defaults():
    state = WatcherState()
    assert state.last_event_ts is None
    assert state.last_event_counter == 0
    assert state.last_status_mtime is None
    assert state.emitted_dimensions == frozenset()


def test_watcher_state_with_initial_last_event_ts():
    ts = datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc)
    state = WatcherState(last_event_ts=ts)
    assert state.last_event_ts == ts


def test_watcher_state_with_emitted_dimensions():
    state = WatcherState(emitted_dimensions=frozenset({"security", "timeliness"}))
    assert "security" in state.emitted_dimensions
    assert "timeliness" in state.emitted_dimensions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import json as _json


def _write_status(run_dir: Path, state: str = "running") -> None:
    (run_dir / "status.json").write_text(_json.dumps({"state": state}))


def _write_dim_eval(run_dir: Path, dim: str, score: int = 90) -> None:
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(exist_ok=True)
    (eval_dir / f"{dim}.json").write_text(
        _json.dumps({"dimension": dim, "score": score}),
    )


def _write_finding_event(run_dir: Path, p: str = "P1", line: int = 1) -> None:
    event_log = EventLogWriter(run_dir / "events.jsonl")
    payload = JudgmentPayload(
        practice_id=p,
        verdict="violation",
        dimension="dim",
        file="x.py",
        line=line,
        reason="r",
        severity="medium",
        snippet="s",
        title="t",
    )
    event_log.emit(JudgmentCreatedEvent(payload=payload))


# ---------------------------------------------------------------------------
# compute_tick tests
# ---------------------------------------------------------------------------

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


def test_compute_tick_handles_malformed_status_json(tmp_path: Path):
    (tmp_path / "status.json").write_text("not valid json {")
    state = WatcherState()
    events, _ = compute_tick(tmp_path, state)
    status_events = [e for e in events if e[0] == "status"]
    assert len(status_events) == 1


# ---------------------------------------------------------------------------
# run_events_generator tests
# ---------------------------------------------------------------------------

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
    from quodeq.api._run_event_stream import run_events_generator

    _write_status(tmp_path, state="done")
    frames = list(run_events_generator(tmp_path, last_event_ts=None, tick_seconds=0.0))
    non_keepalive = [f for f in frames if not f.startswith(":")]
    assert any("event: status" in f for f in non_keepalive)
    assert any("event: done" in f for f in non_keepalive)


def test_run_events_generator_emits_finding_with_event_id(tmp_path: Path):
    from quodeq.api._run_event_stream import run_events_generator

    _write_status(tmp_path, state="running")
    _write_finding_event(tmp_path)
    gen = run_events_generator(tmp_path, last_event_ts=None, tick_seconds=0.0)
    frames = _drain_generator(gen, max_frames=3)
    finding_frames = [f for f in frames if "event: finding" in f]
    assert len(finding_frames) == 1
    # event_id is an ISO timestamp string
    assert "id: " in finding_frames[0]
    # payload id is counter = 1
    data = _json.loads(next(l for l in finding_frames[0].splitlines() if l.startswith("data: "))[6:])
    assert data["id"] == 1


def test_run_events_generator_respects_initial_last_event_ts(tmp_path: Path):
    from quodeq.api._run_event_stream import run_events_generator

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
    data = _json.loads(next(l for l in finding_frames[0].splitlines() if l.startswith("data: "))[6:])
    assert data["practice_id"] == "P2"


def test_run_events_generator_handles_already_terminal_run(tmp_path: Path):
    from quodeq.api._run_event_stream import run_events_generator

    _write_status(tmp_path, state="failed")
    _write_finding_event(tmp_path)
    frames = list(run_events_generator(tmp_path, last_event_ts=None, tick_seconds=0.0))
    non_keepalive = [f for f in frames if not f.startswith(":")]
    assert any("event: status" in f for f in non_keepalive)
    assert any("event: finding" in f for f in non_keepalive)
    assert any("event: done" in f for f in non_keepalive)


def test_run_events_generator_keeps_ticking_after_terminal_done(tmp_path: Path) -> None:
    """Regression: terminal status must NOT close the SSE stream.

    The previous behaviour returned from the generator right after yielding
    the 'done' frame. For a completed run, that meant the SSE lived for only
    one tick — long enough to deliver the initial snapshot, then the server
    closed the connection. Every page that subscribed to ``useGradeStream``
    on a completed run was subscribing to a dead pipe.

    Completed runs are the primary case where users dismiss findings, and
    dismisses must still propagate as scores.updated events. This test pins
    that contract by:
      1. Setting up a run with state='done' and a single finding.
      2. Driving the generator in a thread.
      3. Asserting the initial 'done' frame arrives (clients still get the
         lifecycle signal).
      4. Appending a FINDING_DISMISSED to actions.jsonl.
      5. Asserting a subsequent scores.updated frame arrives — proving the
         generator stayed alive past the terminal event.

    Before the fix this test times out at step 5 because the generator has
    already returned.
    """
    import queue, threading
    from quodeq.api._run_event_stream import run_events_generator
    from quodeq.services.dismissed import dismiss_finding

    project_dir, run_dir = _seed_run_with_finding(tmp_path)
    _write_status(run_dir, state="done")

    frame_q: "queue.Queue[str]" = queue.Queue()
    gen = run_events_generator(run_dir, last_event_ts=None, tick_seconds=0.02)

    def drain() -> None:
        try:
            for frame in gen:
                frame_q.put(frame)
        except Exception as exc:  # noqa: BLE001 — surface drain errors to the test
            frame_q.put(f"__error__: {exc!r}")

    t = threading.Thread(target=drain, daemon=True)
    t.start()

    def wait_for(predicate, deadline_s: float = 2.0) -> list[str]:
        seen: list[str] = []
        deadline = time.monotonic() + deadline_s
        while time.monotonic() < deadline:
            try:
                frame = frame_q.get(timeout=0.05)
            except queue.Empty:
                continue
            seen.append(frame)
            if predicate(frame):
                return seen
        return seen

    # 1. Initial 'done' frame must arrive.
    initial = wait_for(lambda f: "event: done" in f, deadline_s=1.5)
    assert any("event: done" in f for f in initial), (
        f"Initial 'done' frame missing. Frames seen: {initial}"
    )

    # 2. Now dismiss while the generator is (or should be) still ticking.
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    # 3. A scores.updated MUST arrive — proves the generator survived the
    # terminal status and the dismiss propagated through the SSE tick.
    after = wait_for(lambda f: "event: scores.updated" in f, deadline_s=2.0)
    assert any("event: scores.updated" in f for f in after), (
        "Dismiss did not produce a scores.updated frame within 2 s of POST. "
        "Either the generator returned after 'done' (old buggy behaviour), "
        "or compute_tick failed to detect the projection change. "
        f"Frames after dismiss: {after}"
    )


def test_run_events_generator_emits_done_only_once(tmp_path: Path) -> None:
    """Even though the generator now stays open after terminal status, it must
    only emit the 'done' frame ONCE per stream. Otherwise clients tracking
    eval lifecycle would see duplicate terminal signals on every tick."""
    import queue, threading
    from quodeq.api._run_event_stream import run_events_generator

    project_dir, run_dir = _seed_run_with_finding(tmp_path)
    _write_status(run_dir, state="done")

    frame_q: "queue.Queue[str]" = queue.Queue()
    gen = run_events_generator(run_dir, last_event_ts=None, tick_seconds=0.02)

    def drain() -> None:
        for frame in gen:
            frame_q.put(frame)

    threading.Thread(target=drain, daemon=True).start()

    # Drain for ~500 ms (25-ish ticks) and count 'done' frames.
    deadline = time.monotonic() + 0.5
    done_count = 0
    while time.monotonic() < deadline:
        try:
            frame = frame_q.get(timeout=0.05)
        except queue.Empty:
            continue
        if "event: done" in frame:
            done_count += 1
    assert done_count == 1, (
        f"Expected exactly one 'done' frame per stream, got {done_count}"
    )


# ---------------------------------------------------------------------------
# scores.updated event tests
# ---------------------------------------------------------------------------

from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def _seed_run_with_finding(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal run dir with one finding and trigger initial projection."""
    project_dir = tmp_path / "myproject"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    EventLogWriter(run_dir / "events.jsonl").emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1", severity="high",
    )))
    # Trigger projection + grade compute via a read.
    SqliteFindingsRepository(run_dir).list_by_dimension("Security")
    return project_dir, run_dir


def test_compute_tick_emits_scores_updated_when_grades_advance(tmp_path: Path) -> None:
    """When dimension_scores' MAX(completed_at) advances since the last tick,
    compute_tick emits a scores.updated event with the full /scores payload."""
    _project_dir, run_dir = _seed_run_with_finding(tmp_path)

    state = WatcherState()
    events, new_state = compute_tick(run_dir, state)

    grade_events = [e for e in events if e[0] == "scores.updated"]
    assert len(grade_events) == 1, f"Expected one scores.updated event, got: {[e[0] for e in events]}"
    assert new_state.last_grade_fingerprint is not None


def test_compute_tick_does_not_reemit_scores_when_unchanged(tmp_path: Path) -> None:
    """Subsequent ticks against the same projected state do not re-emit scores.updated."""
    _project_dir, run_dir = _seed_run_with_finding(tmp_path)

    state = WatcherState()
    _, state = compute_tick(run_dir, state)  # first tick captures the score

    events, _ = compute_tick(run_dir, state)  # second tick, no change

    grade_events = [e for e in events if e[0] == "scores.updated"]
    assert grade_events == []


def test_compute_tick_emits_scores_updated_after_dismiss(tmp_path: Path) -> None:
    """A dismiss event between ticks causes a fresh scores.updated emission."""
    from quodeq.services.dismissed import dismiss_finding

    project_dir, run_dir = _seed_run_with_finding(tmp_path)

    state = WatcherState()
    _, state = compute_tick(run_dir, state)  # baseline

    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    events, _ = compute_tick(run_dir, state)
    grade_events = [e for e in events if e[0] == "scores.updated"]
    assert len(grade_events) == 1


def test_compute_tick_no_scores_event_when_no_grades_table(tmp_path: Path) -> None:
    """When the run has no projected grades (no findings, no DB), no scores.updated emits."""
    project_dir = tmp_path / "myproject"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    # No events.jsonl at all -- empty run_dir.
    state = WatcherState()
    events, _ = compute_tick(run_dir, state)

    grade_events = [e for e in events if e[0] == "scores.updated"]
    assert grade_events == []


def test_compute_tick_emits_scores_updated_when_all_findings_dismissed(tmp_path: Path) -> None:
    """When all findings are dismissed, dimension_scores ends up empty.
    The next tick must still emit scores.updated to inform clients
    that the previous score state is no longer valid.

    This is the primary justification for using a fingerprint instead of
    MAX(completed_at) for change detection."""
    from quodeq.services.dismissed import dismiss_finding

    project_dir, run_dir = _seed_run_with_finding(tmp_path)

    state = WatcherState()
    _, state = compute_tick(run_dir, state)  # baseline: dimension_scores populated

    # Dismiss the only finding → dimension_scores will become empty after re-projection.
    dismiss_finding(project_dir, {"req": "R1", "file": "a.py", "line": 10})

    events, new_state = compute_tick(run_dir, state)
    grade_events = [e for e in events if e[0] == "scores.updated"]

    assert len(grade_events) == 1, (
        "scores.updated must fire when dimension_scores transitions to empty; "
        f"events were: {[e[0] for e in events]}"
    )
    # The fingerprint should reflect the empty state.
    assert new_state.last_grade_fingerprint != state.last_grade_fingerprint
