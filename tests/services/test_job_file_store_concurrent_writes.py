"""Tests for _job_file_store.py: concurrent writers of one job never publish a torn file."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from quodeq.services.jobs import FileJobStore, Job


class TestConcurrentSameJobWrites:
    """Two writers on the same job id never publish a torn file."""

    def test_never_reuses_a_temp_path(self, tmp_path: Path, monkeypatch):
        """A shared ``{job_id}.tmp`` lets one writer's replace publish the other's still-open file."""
        store = FileJobStore(persist_dir=tmp_path)
        seen: list[str] = []
        real_replace = os.replace

        def spy(src, dst):
            seen.append(str(src))
            return real_replace(src, dst)

        monkeypatch.setattr(os, "replace", spy)
        store.put(Job("shared", "running", ["echo"], "now", None, None))
        store.put(Job("shared", "running", ["echo"], "now", None, None))
        assert len(seen) == 2 and seen[0] != seen[1]

    def test_concurrent_writers_never_publish_invalid_json(self, tmp_path: Path):
        """A reader polling while two threads hammer put() on one job id must never see invalid JSON."""
        store = FileJobStore(persist_dir=tmp_path)
        path = tmp_path / "shared.json"
        stop = threading.Event()
        failures: list[str] = []

        def writer(tag: str) -> None:
            i = 0
            while not stop.is_set():
                job = Job("shared", "running", ["echo", tag], "now", None, None)
                job.logs.append((tag * 200) + str(i))
                store.put(job)
                i += 1

        def reader() -> None:
            deadline = time.time() + 0.6
            while time.time() < deadline:
                try:
                    text = path.read_text(encoding="utf-8") if path.exists() else ""
                except OSError:
                    continue
                if text:
                    try:
                        json.loads(text)
                    except json.JSONDecodeError as exc:
                        failures.append(str(exc))

        threads = [threading.Thread(target=writer, args=(t,)) for t in ("a", "b")]
        threads.append(threading.Thread(target=reader))
        for t in threads:
            t.start()
        stop.wait(0.6)
        stop.set()
        for t in threads:
            t.join(timeout=5)
        assert failures == []
