"""Tests for clone_lock (audit finding C2): git mutations on one shared
clone directory -- refresh vs refresh vs publish -- must be serialized
behind one process-wide reentrant lock, not left to interleave.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from quodeq.services import shared_publish, shared_repo
from quodeq.services.shared_publish import publish_project
from quodeq.services.shared_repo import clone_lock, ensure_shared_clone, refresh_shared_clone

# The thread join()/wait() calls below are deadlock guards, not performance
# assertions: a genuine clone-lock deadlock hangs forever, so any generous
# ceiling still trips on a real hang. 5s was too tight for the real git
# clone/commit/push subprocesses these tests spawn over file://, which flaked
# on loaded Windows CI runners. A large budget keeps the deadlock signal while
# removing the timing sensitivity.
_DEADLOCK_GUARD_TIMEOUT = 60.0


def _bare_origin(tmp_path: Path, name: str = "origin.git") -> str:
    origin = tmp_path / name
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    return f"file://{origin}"


def _local_project(root: Path, project_id: str = "proj-1") -> None:
    project = root / project_id
    run = project / "run-1"
    (run / "evidence").mkdir(parents=True)
    (project / "repository_info.json").write_text('{"name":"demo"}')
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run / "dimensions.json").write_text("{}")
    (run / "events.jsonl").write_text("{}\n")


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")


def test_clone_lock_keyed_by_path_and_reentrant(tmp_path, monkeypatch):
    """clone_lock returns the SAME RLock for the same resolved clone path,
    a DIFFERENT one for a different clone, and allows the same thread to
    acquire it more than once (RLock, not Lock)."""
    lock_a1 = clone_lock("file:///a.git")
    lock_a2 = clone_lock("file:///a.git")
    lock_b = clone_lock("file:///b.git")

    assert lock_a1 is lock_a2
    assert lock_a1 is not lock_b

    assert lock_a1.acquire(timeout=1)
    try:
        assert lock_a1.acquire(timeout=1)  # reentrant on the same thread
        lock_a1.release()
    finally:
        lock_a1.release()


def test_refresh_waits_for_publish(tmp_path, monkeypatch):
    """A refresh entered while publish holds the clone lock must not
    interleave: record git-op ordering with a monkeypatched run_git that
    sleeps inside publish's staging window, fire refresh_shared_clone from
    a thread, assert its first git op timestamp is after publish's last."""
    url = _bare_origin(tmp_path)
    root = tmp_path / "evaluations"
    _local_project(root)
    # Pre-clone so publish_project's own ensure_shared_clone call is a
    # no-op filesystem check (no git call), keeping the recorded timeline
    # focused on the commit/push vs refresh ordering this test targets.
    assert ensure_shared_clone(url) is not None

    events: list[tuple[str, float, str]] = []
    events_lock = threading.Lock()
    commit_reached = threading.Event()
    real_run_git = shared_repo.run_git

    def _recording_run_git(args, *, cwd=None, timeout=None):
        op = args[0] if args else "?"
        if op == "commit":
            commit_reached.set()
            time.sleep(0.3)  # widen publish's staging window
        result = real_run_git(args, cwd=cwd, timeout=timeout)
        with events_lock:
            events.append((op, time.monotonic(), threading.current_thread().name))
        return result

    # publish_project and shared_repo's refresh/ensure helpers each hold
    # their own imported reference to run_git, so both must be patched.
    monkeypatch.setattr(shared_repo, "run_git", _recording_run_git)
    monkeypatch.setattr(shared_publish, "run_git", _recording_run_git)

    publish_errors: list[BaseException] = []

    def _do_publish():
        try:
            publish_project("proj-1", url, evaluations_root=root)
        except BaseException as exc:  # noqa: BLE001 - surfaced via assertion below
            publish_errors.append(exc)

    refresh_errors: list[BaseException] = []

    def _fire_refresh():
        try:
            refresh_shared_clone(url)
        except BaseException as exc:  # noqa: BLE001
            refresh_errors.append(exc)

    publish_thread = threading.Thread(target=_do_publish, name="publish")
    refresh_thread = threading.Thread(target=_fire_refresh, name="refresh")

    publish_thread.start()
    assert commit_reached.wait(timeout=_DEADLOCK_GUARD_TIMEOUT), (
        "publish never reached its commit step"
    )
    refresh_thread.start()

    publish_thread.join(timeout=_DEADLOCK_GUARD_TIMEOUT)
    refresh_thread.join(timeout=_DEADLOCK_GUARD_TIMEOUT)

    assert not publish_thread.is_alive(), "publish_project deadlocked"
    assert not refresh_thread.is_alive(), "refresh_shared_clone deadlocked"
    assert not publish_errors, publish_errors
    assert not refresh_errors, refresh_errors

    publish_times = [t for _, t, name in events if name == "publish"]
    refresh_times = [t for _, t, name in events if name == "refresh"]
    assert publish_times, "publish recorded no git ops"
    assert refresh_times, "refresh recorded no git ops"

    # The refresh thread blocked on clone_lock until publish released it, so
    # every git op refresh issued happened strictly after publish's last one.
    assert min(refresh_times) > max(publish_times)


def test_clone_lock_is_reentrant_for_publish_internal_refresh(tmp_path):
    """publish_project's own refresh_shared_clone call under the held lock
    completes (RLock), no deadlock (guard with a join timeout)."""
    url = _bare_origin(tmp_path)
    root = tmp_path / "evaluations"
    _local_project(root)

    results: list[tuple[str, object]] = []

    def _do_publish():
        try:
            count = publish_project("proj-1", url, evaluations_root=root)
            results.append(("ok", count))
        except BaseException as exc:  # noqa: BLE001 - surfaced via assertion below
            results.append(("error", exc))

    thread = threading.Thread(target=_do_publish, name="publish")
    thread.start()
    thread.join(timeout=_DEADLOCK_GUARD_TIMEOUT)

    assert not thread.is_alive(), (
        "publish_project deadlocked acquiring its own clone lock reentrantly "
        "via ensure_shared_clone / refresh_shared_clone"
    )
    assert results and results[0] == ("ok", 1), results
