"""The access ladder's env reaches git on shared clone and refresh, not only the cache path."""
from __future__ import annotations

import subprocess

from quodeq.data.fs import shared_repo
from quodeq.data.fs.shared_repo_git import CACHE_ENV

_URL = "https://github.com/o/r.git"


def _recording_run(calls):
    def fake_run(cmd, **kw):
        calls.append((cmd, kw["env"]))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return fake_run


def test_ensure_shared_clone_passes_env_to_git(tmp_path, monkeypatch):
    env = {CACHE_ENV: str(tmp_path), "GIT_CONFIG_COUNT": "1"}
    calls = []
    monkeypatch.setattr("quodeq.data.fs.shared_repo_git.subprocess.run", _recording_run(calls))
    shared_repo.ensure_shared_clone(_URL, env)
    clone = [e for cmd, e in calls if "clone" in cmd]
    assert clone and clone[0]["GIT_CONFIG_COUNT"] == "1"


def test_refresh_shared_clone_passes_env_to_fetch_and_reset(tmp_path, monkeypatch):
    env = {CACHE_ENV: str(tmp_path), "GIT_CONFIG_COUNT": "1"}
    (shared_repo.shared_repo_path(_URL, env) / ".git").mkdir(parents=True)
    calls = []
    monkeypatch.setattr("quodeq.data.fs.shared_repo_git.subprocess.run", _recording_run(calls))
    assert shared_repo.refresh_shared_clone(_URL, env) == (True, "")
    verbs = {cmd[1]: e for cmd, e in calls}
    assert verbs["fetch"]["GIT_CONFIG_COUNT"] == "1" and verbs["reset"]["GIT_CONFIG_COUNT"] == "1"
