"""Every git subprocess inherits the prompt-disabled floor and a closed stdin."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

from quodeq.data.fs.repo_clone import GitCloneClient
from quodeq.data.fs.shared_repo_git import git_env, run_git
from quodeq.data.git_cli import GIT_PROMPT_GUARD, git_env_floor


def test_floor_layers_the_guard_over_the_given_env():
    out = git_env_floor({"PATH": "/usr/bin", "GIT_TERMINAL_PROMPT": "1"})
    assert out["PATH"] == "/usr/bin"
    assert out["GIT_TERMINAL_PROMPT"] == "0"
    assert out["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert out["LC_ALL"] == "C" and out["LANG"] == "C"
    assert GIT_PROMPT_GUARD == {"GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1", "LC_ALL": "C", "LANG": "C"}


def test_floor_keeps_an_injected_empty_env_empty_apart_from_the_guard():
    assert git_env_floor({}) == GIT_PROMPT_GUARD


def test_shared_repo_git_env_is_the_floor():
    assert git_env({"X": "1"}) == git_env_floor({"X": "1"})


def test_clone_progress_disables_prompts_and_closes_stdin(tmp_path):
    with patch("quodeq.data.fs.repo_clone.subprocess.run") as run_mock:
        GitCloneClient({"PATH": "/usr/bin"}).clone_progress("https://x/y.git", tmp_path / "d", [], timeout_s=5)
    kwargs = run_mock.call_args.kwargs
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_clone_legacy_disables_prompts_and_closes_stdin(tmp_path):
    with patch("quodeq.data.fs.repo_clone.subprocess.run") as run_mock:
        GitCloneClient({"PATH": "/usr/bin"}).clone_legacy("https://x/y.git", tmp_path / "d", timeout_s=5)
    kwargs = run_mock.call_args.kwargs
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kwargs["stdin"] is subprocess.DEVNULL


def test_shared_run_git_still_closes_stdin():
    with patch("quodeq.data.fs.shared_repo_git.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = ""
        run_mock.return_value.stderr = ""
        run_git(["version"], env={"PATH": "/usr/bin"})
    kwargs = run_mock.call_args.kwargs
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
