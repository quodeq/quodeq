"""Tests for the cross-process FileQueue."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from quodeq.analysis.subagents.file_queue import FileQueue, FileQueueError


SAMPLE_FILES = [f"src/file_{i}.py" for i in range(30)]


class TestInit:
    def test_creates_queue_file(self, tmp_path: Path) -> None:
        qp = tmp_path / "queue.json"
        FileQueue(qp, SAMPLE_FILES)
        state = json.loads(qp.read_text())
        assert state["version"] == 1
        assert state["pending"] == SAMPLE_FILES
        assert state["taken"] == []

    def test_opens_existing_queue(self, tmp_path: Path) -> None:
        qp = tmp_path / "queue.json"
        FileQueue(qp, SAMPLE_FILES)
        q2 = FileQueue(qp)  # no files arg — opens existing
        assert q2.remaining() == len(SAMPLE_FILES)

    def test_raises_if_file_missing_and_no_files(self, tmp_path: Path) -> None:
        with pytest.raises(FileQueueError, match="not found"):
            FileQueue(tmp_path / "nonexistent.json")

    def test_empty_file_list(self, tmp_path: Path) -> None:
        qp = tmp_path / "queue.json"
        q = FileQueue(qp, [])
        assert q.remaining() == 0
        assert q.take(5) == []


class TestTake:
    def test_basic_take(self, tmp_path: Path) -> None:
        q = FileQueue(tmp_path / "q.json", SAMPLE_FILES)
        batch = q.take(5)
        assert batch == SAMPLE_FILES[:5]
        assert q.remaining() == 25

    def test_take_more_than_available(self, tmp_path: Path) -> None:
        q = FileQueue(tmp_path / "q.json", ["a.py", "b.py"])
        batch = q.take(10)
        assert batch == ["a.py", "b.py"]
        assert q.remaining() == 0

    def test_take_from_empty_queue(self, tmp_path: Path) -> None:
        q = FileQueue(tmp_path / "q.json", [])
        assert q.take(5) == []

    def test_take_zero(self, tmp_path: Path) -> None:
        q = FileQueue(tmp_path / "q.json", ["a.py"])
        assert q.take(0) == []
        assert q.remaining() == 1

    def test_take_negative(self, tmp_path: Path) -> None:
        q = FileQueue(tmp_path / "q.json", ["a.py"])
        assert q.take(-1) == []
        assert q.remaining() == 1

    def test_sequential_takes_drain_queue(self, tmp_path: Path) -> None:
        q = FileQueue(tmp_path / "q.json", SAMPLE_FILES)
        all_taken: list[str] = []
        while True:
            batch = q.take(7)
            if not batch:
                break
            all_taken.extend(batch)
        assert all_taken == SAMPLE_FILES
        assert q.remaining() == 0

    def test_take_records_agent_id(self, tmp_path: Path) -> None:
        q = FileQueue(tmp_path / "q.json", SAMPLE_FILES)
        q.take(3, agent_id="agent-0")
        q.take(3, agent_id="agent-1")
        log = q.taken_log()
        assert len(log) == 2
        assert log[0]["agent"] == "agent-0"
        assert log[1]["agent"] == "agent-1"
        assert len(log[0]["files"]) == 3
        assert "ts" in log[0]


class TestTakenLog:
    def test_all_taken_files(self, tmp_path: Path) -> None:
        q = FileQueue(tmp_path / "q.json", SAMPLE_FILES)
        q.take(10, agent_id="a")
        q.take(10, agent_id="b")
        q.take(10, agent_id="c")
        assert q.all_taken_files() == SAMPLE_FILES
        assert q.remaining() == 0

    def test_empty_log_initially(self, tmp_path: Path) -> None:
        q = FileQueue(tmp_path / "q.json", SAMPLE_FILES)
        assert q.taken_log() == []
        assert q.all_taken_files() == []


class TestPersistence:
    def test_survives_reopen(self, tmp_path: Path) -> None:
        qp = tmp_path / "q.json"
        q1 = FileQueue(qp, SAMPLE_FILES)
        q1.take(10, agent_id="a")

        q2 = FileQueue(qp)  # reopen
        assert q2.remaining() == 20
        assert len(q2.taken_log()) == 1
        batch = q2.take(5, agent_id="b")
        assert batch == SAMPLE_FILES[10:15]

    def test_reinit_overwrites(self, tmp_path: Path) -> None:
        qp = tmp_path / "q.json"
        q1 = FileQueue(qp, SAMPLE_FILES)
        q1.take(10)
        # Re-init with new file list overwrites
        q2 = FileQueue(qp, ["new.py"])
        assert q2.remaining() == 1
        assert q2.taken_log() == []


class TestCorruptionHandling:
    def test_corrupted_json_raises(self, tmp_path: Path) -> None:
        qp = tmp_path / "q.json"
        qp.write_text("not json {{{")
        with pytest.raises(FileQueueError, match="corrupted"):
            FileQueue(qp).remaining()

    def test_missing_pending_key_raises(self, tmp_path: Path) -> None:
        qp = tmp_path / "q.json"
        qp.write_text(json.dumps({"version": 1, "taken": []}))
        with pytest.raises(FileQueueError, match="pending"):
            FileQueue(qp).remaining()

    def test_missing_taken_key_raises(self, tmp_path: Path) -> None:
        qp = tmp_path / "q.json"
        qp.write_text(json.dumps({"version": 1, "pending": []}))
        with pytest.raises(FileQueueError, match="taken"):
            FileQueue(qp).remaining()


class TestConcurrency:
    def test_no_file_assigned_twice_threads(self, tmp_path: Path) -> None:
        """5 threads each calling take(3) — no file duplicated, all consumed."""
        files = [f"src/f{i}.py" for i in range(50)]
        qp = tmp_path / "q.json"
        FileQueue(qp, files)

        results: list[list[str]] = []

        def worker(agent_id: str) -> list[str]:
            q = FileQueue(qp)
            taken: list[str] = []
            while True:
                batch = q.take(3, agent_id=agent_id)
                if not batch:
                    break
                taken.extend(batch)
            return taken

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(worker, f"agent-{i}") for i in range(5)]
            for f in futures:
                results.append(f.result())

        all_taken = [f for batch in results for f in batch]
        assert sorted(all_taken) == sorted(files), "Some files were lost or duplicated"
        assert len(all_taken) == len(files), f"Expected {len(files)}, got {len(all_taken)}"

    def test_no_file_assigned_twice_many_threads(self, tmp_path: Path) -> None:
        """10 threads, 200 files, take(1) — maximum contention."""
        files = [f"src/f{i}.py" for i in range(200)]
        qp = tmp_path / "q.json"
        FileQueue(qp, files)

        results: list[list[str]] = []

        def worker(agent_id: str) -> list[str]:
            q = FileQueue(qp)
            taken: list[str] = []
            while True:
                batch = q.take(1, agent_id=agent_id)
                if not batch:
                    break
                taken.extend(batch)
            return taken

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(worker, f"agent-{i}") for i in range(10)]
            for f in futures:
                results.append(f.result())

        all_taken = [f for batch in results for f in batch]
        assert sorted(all_taken) == sorted(files)
        assert len(all_taken) == len(files)

        # Verify taken log accounts for everything
        q = FileQueue(qp)
        assert q.remaining() == 0
        assert sorted(q.all_taken_files()) == sorted(files)
