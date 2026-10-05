"""ensure_shared_clone / refresh_shared_clone forward git progress to a callback."""
from __future__ import annotations

from pathlib import Path

from quodeq.data.fs import shared_repo
from quodeq.core.types.sync_phase import SyncPhase
from quodeq.data.fs.git_progress import ProgressUpdate
from quodeq.data.fs.shared_repo import ensure_shared_clone, refresh_shared_clone, shared_repo_path

_URL = "https://example.invalid/team/results.git"


def _fake_stream(lines, ok=True):
    calls = []

    def run(args, *, cwd=None, timeout, env=None, on_line):
        calls.append((args, cwd, timeout, env))
        for line in lines:
            on_line(line)
        if ok:
            (Path(cwd) if cwd else Path(str(args[-1]))).mkdir(parents=True, exist_ok=True)
        return ok, "tail"
    run.calls = calls
    return run


def test_clone_streams_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path))
    run = _fake_stream(["Cloning into 'x'...", "Receiving objects:  45% (1/2), 1.00 MiB", "Resolving deltas: 100% (1/1), done."])
    monkeypatch.setattr(shared_repo, "run_git_streaming", run)
    seen = []
    repo = ensure_shared_clone(_URL, env={"QUODEQ_CACHE_ROOT": str(tmp_path)}, progress=seen.append)
    assert repo == shared_repo_path(_URL, {"QUODEQ_CACHE_ROOT": str(tmp_path)})
    assert run.calls[0][0][:3] == ["clone", "--progress", "--"]
    assert seen == [ProgressUpdate(45, 1048576), ProgressUpdate(100, None, SyncPhase.RESOLVING)]


def test_clone_without_callback_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(shared_repo, "run_git_streaming", _fake_stream(["Receiving objects: 50% (1/2)"]))
    assert ensure_shared_clone(_URL, env={"QUODEQ_CACHE_ROOT": str(tmp_path)}) is not None


def test_clone_failure_removes_dir_and_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(shared_repo, "run_git_streaming", _fake_stream([], ok=False))
    assert ensure_shared_clone(_URL, env={"QUODEQ_CACHE_ROOT": str(tmp_path)}) is None
    assert not shared_repo_path(_URL, {"QUODEQ_CACHE_ROOT": str(tmp_path)}).exists()


def test_refresh_streams_fetch_progress_and_keeps_reset_blocking(tmp_path, monkeypatch):
    env = {"QUODEQ_CACHE_ROOT": str(tmp_path)}
    repo = shared_repo_path(_URL, env)
    (repo / ".git").mkdir(parents=True)
    stream = _fake_stream(["Receiving objects:  80% (8/10), 2.00 MiB"])
    monkeypatch.setattr(shared_repo, "run_git_streaming", stream)
    blocking = []
    monkeypatch.setattr(shared_repo, "run_git", lambda args, **kw: (blocking.append(args), (True, ""))[1])
    seen = []
    ok, reason = refresh_shared_clone(_URL, env, progress=seen.append)
    assert ok and reason == ""
    assert stream.calls[0][0][:3] == ["fetch", "--progress", "origin"]
    assert blocking[-1][:2] == ["reset", "--hard"]
    assert seen == [ProgressUpdate(80, 2097152)]
