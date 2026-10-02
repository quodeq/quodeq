"""The access ladder's env reaches git on shared clone and refresh, not only the cache path.

Clone and fetch go through the streaming runner (a Popen in git_stream); reset
keeps the blocking runner (subprocess.run in shared_repo_git).
"""
from __future__ import annotations

import os
import subprocess

from quodeq.data.fs import shared_repo
from quodeq.data.fs.shared_repo_git import CACHE_ENV

_URL = "https://github.com/o/r.git"


def _recording_run(calls):
    def fake_run(cmd, **kw):
        calls.append((cmd, kw["env"]))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return fake_run


class _FakePopen:
    """Popen stand-in that records cmd/env and exits 0 with empty stderr."""

    calls: list = []

    def __init__(self, cmd, **kw):
        type(self).calls.append((cmd, kw["env"]))
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        self.stderr = os.fdopen(read_fd, "rb")
        self.pid = 4_194_304  # no such process: a stray killpg raises instead of hitting the runner's group
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


def _patch_popen(monkeypatch):
    calls: list = []
    popen = type("RecordingPopen", (_FakePopen,), {"calls": calls})
    monkeypatch.setattr("quodeq.data.fs.git_stream.subprocess.Popen", popen)
    return calls


def test_ensure_shared_clone_passes_env_to_git(tmp_path, monkeypatch):
    env = {CACHE_ENV: str(tmp_path), "GIT_CONFIG_COUNT": "1"}
    calls = _patch_popen(monkeypatch)
    shared_repo.ensure_shared_clone(_URL, env)
    clone = [e for cmd, e in calls if "clone" in cmd]
    assert clone and clone[0]["GIT_CONFIG_COUNT"] == "1"


def test_refresh_shared_clone_passes_env_to_fetch_and_reset(tmp_path, monkeypatch):
    env = {CACHE_ENV: str(tmp_path), "GIT_CONFIG_COUNT": "1"}
    (shared_repo.shared_repo_path(_URL, env) / ".git").mkdir(parents=True)
    streamed = _patch_popen(monkeypatch)
    blocking: list = []
    monkeypatch.setattr("quodeq.data.fs.shared_repo_git.subprocess.run", _recording_run(blocking))
    assert shared_repo.refresh_shared_clone(_URL, env) == (True, "")
    fetch = [e for cmd, e in streamed if "fetch" in cmd]
    reset = [e for cmd, e in blocking if "reset" in cmd]
    assert fetch and fetch[0]["GIT_CONFIG_COUNT"] == "1"
    assert reset and reset[0]["GIT_CONFIG_COUNT"] == "1"
