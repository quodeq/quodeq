"""Tests for quodeq.analysis.subagents._heartbeat — progress reporting."""
from __future__ import annotations

import json
import threading
from pathlib import Path

from quodeq.analysis.subagents._heartbeat import (
    HeartbeatContext,
    _read_tally,
    _HEARTBEAT_FMT,
    heartbeat_loop,
)
from quodeq.analysis.subagents.jsonl_utils import FindingTally
from tests._timeouts import budget


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
    def test_format_renders_expected_segments(self) -> None:
        line = _HEARTBEAT_FMT.format(
            dimension="security", mins=1, secs=2,
            active=2, plural="s",
            taken=10, total_files=30, remaining=20,
            violations=2, compliance=5, suppressed="", quarantined="",
        )
        assert line.startswith("[security] 1m02s")
        assert "2 v · 5 c" in line
        # The remaining count is dropped: 30 minus 10 already says it.
        assert "files 10/30 |" in line
        assert "left" not in line
        assert line.endswith("2 agents")
        assert "findings" not in line
        assert "total" not in line

    def test_format_uses_singular_for_one_active_agent(self) -> None:
        line = _HEARTBEAT_FMT.format(
            dimension="security", mins=0, secs=5,
            active=1, plural="",
            taken=1, total_files=2, remaining=1,
            violations=0, compliance=0, suppressed="", quarantined="",
        )
        assert line.endswith("1 agent")

    def test_suppressed_segment_follows_the_compliance_count(self) -> None:
        line = _HEARTBEAT_FMT.format(
            dimension="reliability", mins=16, secs=1,
            active=1, plural="",
            taken=34, total_files=34, remaining=0,
            violations=122, compliance=261, suppressed=" · 339 s",
            quarantined="",
        )
        assert "122 v · 261 c · 339 s |" in line

    def test_no_suppressed_segment_when_nothing_is_hidden(self) -> None:
        """A project with no dismissals must keep the pre-existing line shape."""
        line = _HEARTBEAT_FMT.format(
            dimension="reliability", mins=1, secs=0,
            active=1, plural="",
            taken=1, total_files=2, remaining=1,
            violations=7, compliance=3, suppressed="", quarantined="",
        )
        assert "7 v · 3 c |" in line

    def test_unmapped_segment_only_appears_when_something_was_quarantined(self) -> None:
        """A clean run keeps the line's original shape."""
        kwargs = dict(
            dimension="security", mins=0, secs=5, active=1, plural="",
            taken=1, total_files=2, remaining=1, violations=3, compliance=0,
            suppressed="",
        )
        assert "3 v · 0 c |" in _HEARTBEAT_FMT.format(quarantined="", **kwargs)
        assert "3 v · 0 c · 1 u |" in _HEARTBEAT_FMT.format(
            quarantined=" · 1 u", **kwargs,
        )

    def test_both_exclusion_segments_render_together(self) -> None:
        """Suppressed comes first, then unmapped, and neither swallows the other."""
        line = _HEARTBEAT_FMT.format(
            dimension="maintainability", mins=2, secs=0,
            active=1, plural="",
            taken=5, total_files=5, remaining=0,
            violations=570, compliance=168,
            suppressed=" · 12 s", quarantined=" · 1 u",
        )
        assert "570 v · 168 c · 12 s · 1 u |" in line


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
        thread.join(timeout=budget(0.2))
        stop.set()
        thread.join(timeout=budget(1.0))

        assert emitted, "heartbeat should emit at least one log line"
        assert "[security]" in emitted[0]
        assert "1 v · 0 c" in emitted[0]
