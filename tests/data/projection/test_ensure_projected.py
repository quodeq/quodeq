from __future__ import annotations

import threading
from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.projection.projector import ProjectionResult, Projector


def _write_events(log: Path, n: int, start: int = 0) -> None:
    writer = EventLogWriter(log)
    for i in range(start, start + n):
        payload = JudgmentPayload(
            practice_id=f"P{i}", verdict="violation", dimension="Security",
            file=f"f{i}.py", line=i + 1, reason="r",
        )
        writer.emit(JudgmentCreatedEvent(payload=payload))


def test_ensure_no_op_when_size_matches(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 3)
    projector = Projector()
    projector.project(log, tmp_path)

    result = projector.ensure_projected(log, tmp_path)

    assert result == ProjectionResult(events_projected=0, rebuilt=False)


def test_ensure_projects_when_size_grows(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 2)
    projector = Projector()
    projector.project(log, tmp_path)

    _write_events(log, 3, start=2)
    result = projector.ensure_projected(log, tmp_path)

    assert result.events_projected == 3
    assert result.rebuilt is False


def test_ensure_bootstrap_when_no_size_stored(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 4)

    result = Projector().ensure_projected(log, tmp_path)

    assert result.events_projected == 4
    assert result.rebuilt is True


def test_concurrent_ensure_projects_once(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    _write_events(log, 3)
    # Prime once so both threads see a stored size that doesn't match yet.
    Projector().project(log, tmp_path)
    _write_events(log, 2, start=3)

    projector = Projector()
    call_count = 0
    real_project = projector.project
    call_lock = threading.Lock()

    def spy(*args, **kwargs):
        nonlocal call_count
        with call_lock:
            call_count += 1
        return real_project(*args, **kwargs)

    projector.project = spy  # type: ignore[method-assign]

    barrier = threading.Barrier(2)

    def run() -> None:
        barrier.wait()
        projector.ensure_projected(log, tmp_path)

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert call_count == 1
