"""mark_run_consolidated — the one place a run's findings become "carried".

A cache entry is born unconsolidated. Only a run that reaches state=done
flips its entries, which is what lets the live feed show a cancelled run's
replayed findings as this scan's own.

Every failure mode here is a no-op by design: the function runs as a
post-scan side effect outside the run lifecycle, so a raise would be the
one thing that could turn a completed run into a failed one.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from quodeq.analysis.cache.consolidation import mark_run_consolidated
from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.local import LocalFileBackend


def _entry(key: str, *, consolidated: bool = False) -> CacheEntry:
    return CacheEntry(
        key=key, schema_version=1,
        findings=[{"file": "a.py", "line": 1, "t": "violation"}],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model", consolidated=consolidated,
    )


def _run_dir(tmp_path: Path, state: str | None, sidecars: dict[str, dict]) -> Path:
    run_dir = tmp_path / "reports" / "proj" / "run1"
    evidence = run_dir / "evidence"
    evidence.mkdir(parents=True)
    if state is not None:
        (run_dir / "status.json").write_text(json.dumps({"state": state}))
    for name, payload in sidecars.items():
        (evidence / name).write_text(json.dumps(payload))
    return run_dir


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


def test_done_run_flips_dispatched_entries(tmp_path: Path, cache):
    cache.put("key1", _entry("key1"))
    run_dir = _run_dir(
        tmp_path, "done", {"security_dispatch_keys.json": {"a.py": "key1"}},
    )

    mark_run_consolidated(run_dir, cache)

    assert cache.get("key1").consolidated is True


def test_done_run_flips_replayed_unconsolidated_entries(tmp_path: Path, cache):
    """The findings a completed run replayed are now in ITS report too."""
    cache.put("key2", _entry("key2"))
    run_dir = _run_dir(
        tmp_path, "done",
        {"security_replayed_unconsolidated_keys.json": {"a.py": "key2"}},
    )

    mark_run_consolidated(run_dir, cache)

    assert cache.get("key2").consolidated is True


def test_done_run_flips_both_sidecars_across_dimensions(tmp_path: Path, cache):
    for key in ("key1", "key2", "key3"):
        cache.put(key, _entry(key))
    run_dir = _run_dir(tmp_path, "done", {
        "security_dispatch_keys.json": {"a.py": "key1"},
        "flexibility_dispatch_keys.json": {"b.py": "key2"},
        "security_replayed_unconsolidated_keys.json": {"c.py": "key3"},
    })

    mark_run_consolidated(run_dir, cache)

    assert all(cache.get(k).consolidated is True for k in ("key1", "key2", "key3"))


@pytest.mark.parametrize("state", ["cancelled", "failed", "in_progress", "pending"])
def test_non_done_run_leaves_entries_unconsolidated(tmp_path: Path, cache, state):
    """The whole feature. A run the user cancelled with "keep findings" never
    consolidated anything, so its findings must replay as new."""
    cache.put("key1", _entry("key1"))
    run_dir = _run_dir(
        tmp_path, state, {"security_dispatch_keys.json": {"a.py": "key1"}},
    )

    mark_run_consolidated(run_dir, cache)

    assert cache.get("key1").consolidated is False


def test_missing_status_json_leaves_entries_unconsolidated(tmp_path: Path, cache):
    """A killed process may never have written a terminal status."""
    cache.put("key1", _entry("key1"))
    run_dir = _run_dir(
        tmp_path, None, {"security_dispatch_keys.json": {"a.py": "key1"}},
    )

    mark_run_consolidated(run_dir, cache)

    assert cache.get("key1").consolidated is False


def test_corrupt_status_json_leaves_entries_unconsolidated(tmp_path: Path, cache):
    cache.put("key1", _entry("key1"))
    run_dir = _run_dir(
        tmp_path, None, {"security_dispatch_keys.json": {"a.py": "key1"}},
    )
    (run_dir / "status.json").write_text("{not json")

    mark_run_consolidated(run_dir, cache)

    assert cache.get("key1").consolidated is False


def test_corrupt_sidecar_does_not_stop_the_other_sidecars(tmp_path: Path, cache):
    cache.put("key1", _entry("key1"))
    run_dir = _run_dir(tmp_path, "done", {
        "security_dispatch_keys.json": {"a.py": "key1"},
    })
    (run_dir / "evidence" / "flexibility_dispatch_keys.json").write_text("{not json")

    mark_run_consolidated(run_dir, cache)

    assert cache.get("key1").consolidated is True


def test_missing_entry_is_skipped(tmp_path: Path, cache):
    """A file that errored mid-dispatch has a key in the sidecar but no entry.
    The key must be skipped, not written back as a fabricated entry."""
    run_dir = _run_dir(
        tmp_path, "done", {"security_dispatch_keys.json": {"a.py": "ghost"}},
    )

    mark_run_consolidated(run_dir, cache)

    assert cache.get("ghost") is None
    assert list((tmp_path / "cache").rglob("entry.json")) == []


def test_a_raising_backend_never_propagates(tmp_path: Path, caplog):
    """Fail-soft is the contract, not a comment. This runs outside the run
    lifecycle precisely so it can never flip a done run to failed.

    caplog proves the failing branch was actually reached: without it, a test
    that merely "does not raise" would also pass if the function had bailed
    early for an unrelated reason and never touched the backend at all."""
    class _Exploding:
        def __init__(self) -> None:
            self.touched = 0

        def get(self, key):
            self.touched += 1
            raise RuntimeError("disk on fire")

        def put(self, key, entry):
            raise AssertionError("put must never be reached after get raised")

    backend = _Exploding()
    run_dir = _run_dir(
        tmp_path, "done", {"security_dispatch_keys.json": {"a.py": "key1"}},
    )

    with caplog.at_level(logging.WARNING):
        mark_run_consolidated(run_dir, backend)

    assert backend.touched == 1, "the backend was never consulted"
    assert "Could not consolidate cache entry" in caplog.text


def test_missing_evidence_dir_is_a_no_op(tmp_path: Path):
    """No evidence dir means no sidecars, so the cache must not be opened."""
    class _Forbidden:
        def get(self, key):
            raise AssertionError("cache must not be consulted")

        def put(self, key, entry):
            raise AssertionError("cache must not be consulted")

    run_dir = tmp_path / "reports" / "proj" / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(json.dumps({"state": "done"}))

    mark_run_consolidated(run_dir, _Forbidden())


def test_already_consolidated_entries_are_not_rewritten(tmp_path: Path, cache):
    """Avoids rewriting every entry on every run of a fully cached project."""
    class _RecordingPut:
        def __init__(self, inner) -> None:
            self._inner = inner
            self.puts: list[str] = []

        def get(self, key):
            return self._inner.get(key)

        def put(self, key, entry) -> None:
            self.puts.append(key)
            self._inner.put(key, entry)

    cache.put("key1", _entry("key1", consolidated=True))
    recording = _RecordingPut(cache)
    run_dir = _run_dir(
        tmp_path, "done", {"security_dispatch_keys.json": {"a.py": "key1"}},
    )

    mark_run_consolidated(run_dir, recording)

    assert recording.puts == []
