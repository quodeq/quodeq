"""Tests for quodeq.analysis.subagents._heartbeat — progress reporting."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from quodeq.analysis.subagents._heartbeat import (
    HeartbeatContext,
    _format_dup_segment,
    _read_tally,
    _HEARTBEAT_FMT,
    heartbeat_loop,
)
from quodeq.analysis.subagents.jsonl_utils import FindingTally


def _violation(p: str, file: str, line: int) -> str:
    return json.dumps({"p": p, "file": file, "line": line, "t": "violation"})


def _compliance(p: str, file: str, line: int) -> str:
    return json.dumps({"p": p, "file": file, "line": line, "t": "compliance"})


class TestReadTally:
    def test_missing_file(self, tmp_path: Path) -> None:
        tally = _read_tally(tmp_path / "missing.jsonl", threading.Lock())
        assert tally == FindingTally()

    def test_counts_unique_findings(self, tmp_path: Path) -> None:
        p = tmp_path / "evidence.jsonl"
        p.write_text("\n".join([
            _violation("P1", "a.py", 1),
            _compliance("P2", "b.py", 2),
            "",
        ]) + "\n")
        tally = _read_tally(p, threading.Lock())
        assert tally.violations == 1
        assert tally.compliance == 1
        assert tally.duplicates == 0
        assert tally.total == 2

    def test_counts_duplicates(self, tmp_path: Path) -> None:
        """Repeats of (p, file, line, t) collapse — heartbeat should match the
        UI's view of the file, not the raw line count."""
        p = tmp_path / "evidence.jsonl"
        v = _violation("P1", "a.py", 1)
        c = _compliance("P2", "b.py", 2)
        p.write_text("\n".join([v, v, v, c, c]) + "\n")
        tally = _read_tally(p, threading.Lock())
        assert tally.violations == 1
        assert tally.compliance == 1
        assert tally.duplicates == 3


class TestHeartbeatContext:
    def test_creation(self, tmp_path: Path) -> None:
        ctx = HeartbeatContext(
            queue_path=tmp_path / "queue",
            dimension_key="security",
            jsonl_path=tmp_path / "findings.jsonl",
            lock=threading.Lock(),
        )
        assert ctx.dimension_key == "security"


class TestHeartbeatFormat:
    def test_format_includes_duplicates_segment_when_present(self) -> None:
        """The duplicates segment must appear when overlap exists."""
        line = _HEARTBEAT_FMT.format(
            dimension="security", mins=1, secs=2,
            active=2, total_agents=5,
            taken=10, remaining=20,
            findings=7, dup_seg=_format_dup_segment(3),
            violations=2, compliance=5,
        )
        assert "7 findings (3 dup)" in line
        assert "2 violations" in line
        assert "5 compliance" in line

    def test_format_omits_duplicates_segment_when_zero(self) -> None:
        """No `(0 dup)` clutter when there's no overlap."""
        line = _HEARTBEAT_FMT.format(
            dimension="security", mins=1, secs=2,
            active=2, total_agents=5,
            taken=10, remaining=20,
            findings=7, dup_seg=_format_dup_segment(0),
            violations=2, compliance=5,
        )
        assert "7 findings |" in line
        assert "dup" not in line


class TestHeartbeatLoop:
    def test_emits_then_stops(self, tmp_path: Path, monkeypatch) -> None:
        """Smoke test: one tick logs, then stop event ends the loop."""
        evidence = tmp_path / "evidence.jsonl"
        evidence.write_text(_violation("P1", "a.py", 1) + "\n")
        queue = tmp_path / "queue.json"
        queue.write_text(json.dumps({"version": 1, "taken": [], "pending": []}))

        emitted: list[str] = []
        monkeypatch.setattr(
            "quodeq.analysis.subagents._heartbeat.log_info",
            lambda msg: emitted.append(msg),
        )
        # Drive the loop with a tiny interval and stop after one tick.
        monkeypatch.setattr(
            "quodeq.analysis.subagents._heartbeat._HEARTBEAT_INTERVAL", 0.01,
        )
        ctx = HeartbeatContext(
            queue_path=queue, dimension_key="security",
            jsonl_path=evidence, lock=threading.Lock(),
        )
        stop = threading.Event()
        thread = threading.Thread(
            target=heartbeat_loop, args=(stop, {"a-1": False}, ctx),
        )
        thread.start()
        # Wait briefly for at least one tick, then stop.
        thread.join(timeout=0.2)
        stop.set()
        thread.join(timeout=1.0)

        assert emitted, "heartbeat should emit at least one log line"
        assert "[security]" in emitted[0]
        assert "1 violations" in emitted[0]
