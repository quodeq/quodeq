"""launch_argv / find_program never pick a program out of the current directory.

On Windows ``shutil.which`` searches the current directory before PATH for
a bare command name, and scans run with the analysed repository as the
current directory. The fake ``which`` below repeats that search order so
these tests fail if the helper ever hands it a bare name again.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from quodeq.shared.win_launch import find_program, launch_argv

_PATHEXT = ("", ".exe", ".cmd", ".bat")
_SHIM = '@ECHO off\r\n"%_prog%"  "%dp0%\\node_modules\\codex\\bin\\codex.js" %*\r\nREM node\r\n'


def _windows_which(cmd: str, path: str | None = None) -> str | None:
    """shutil.which as it searches on Windows: the current directory first."""
    dirname, name = os.path.split(cmd)
    if dirname:
        dirs = [dirname]
    else:
        dirs = [os.curdir, *(path if path is not None else os.environ.get("PATH", "")).split(os.pathsep)]
    for directory in dirs:
        for ext in _PATHEXT:
            candidate = os.path.join(directory, name + ext)
            if os.path.isfile(candidate):
                return candidate
    return None


def _program(directory: Path, name: str, text: str = "") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_text(text, encoding="utf-8")
    return target


@pytest.fixture
def repo(tmp_path, monkeypatch) -> Path:
    """An analysed repository, made the current directory."""
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.chdir(root)
    return root


def _launch(argv: list[str], path: str) -> list[str]:
    return launch_argv(argv, {"PATH": path}, windows=True, which=_windows_which)


def test_the_fake_which_prefers_the_current_directory(repo, tmp_path):
    _program(repo, "claude.exe")
    _program(tmp_path / "bin", "claude.exe")
    assert _windows_which("claude", path=str(tmp_path / "bin")) == os.path.join(os.curdir, "claude.exe")


def test_cli_in_the_current_directory_is_passed_over(repo, tmp_path):
    _program(repo, "claude.exe")
    installed = _program(tmp_path / "bin", "claude.exe")
    assert _launch(["claude", "-p", "hi"], str(tmp_path / "bin")) == [str(installed), "-p", "hi"]


@pytest.mark.parametrize("name", ["claude.exe", "codex.cmd", "gemini.cmd", "copilot.bat"])
def test_cli_found_only_in_the_current_directory_is_not_found(repo, tmp_path, name):
    _program(repo, name)
    (tmp_path / "bin").mkdir()
    with pytest.raises(FileNotFoundError, match="not found on PATH"):
        _launch([name.split(".")[0], "--version"], str(tmp_path / "bin"))


def test_unknown_program_raises_instead_of_reaching_the_spawn(repo, tmp_path):
    with pytest.raises(FileNotFoundError):
        _launch(["codex", "--version"], str(tmp_path))


def test_empty_path_entries_do_not_mean_the_current_directory(repo, tmp_path):
    _program(repo, "claude.exe")
    with pytest.raises(FileNotFoundError):
        _launch(["claude"], os.pathsep.join(["", str(tmp_path), ""]))


def test_path_entry_naming_the_current_directory_is_honoured(repo, tmp_path):
    here = _program(repo, "claude.exe")
    path = os.pathsep.join([str(tmp_path / "bin"), str(repo)])
    assert _launch(["claude"], path) == [str(here)]


def test_explicit_path_is_used_as_given(repo, tmp_path):
    explicit = _program(repo / "tools", "claude.exe")
    assert _launch([str(explicit), "-p", "hi"], str(tmp_path)) == [str(explicit), "-p", "hi"]


def test_explicit_path_that_is_missing_is_left_for_the_spawn(repo, tmp_path):
    argv = [str(tmp_path / "gone" / "claude.exe")]
    assert _launch(argv, str(tmp_path)) is argv


def test_node_in_the_current_directory_is_passed_over(repo, tmp_path):
    _program(repo, "node.exe")
    node = _program(tmp_path / "nodejs", "node.exe")
    _program(tmp_path / "npm", "codex.cmd", _SHIM)
    script = _program(tmp_path / "npm" / "node_modules" / "codex" / "bin", "codex.js")
    path = os.pathsep.join([str(tmp_path / "npm"), str(tmp_path / "nodejs")])
    assert _launch(["codex", "exec"], path) == [str(node), str(script), "exec"]


def test_node_found_only_in_the_current_directory_is_not_used(repo, tmp_path):
    _program(repo, "node.exe")
    shim = _program(tmp_path / "npm", "codex.cmd", _SHIM)
    _program(tmp_path / "npm" / "node_modules" / "codex" / "bin", "codex.js")
    assert _launch(["codex", "--version"], str(tmp_path / "npm")) == [str(shim), "--version"]


def test_path_defaults_to_this_process(repo, tmp_path, monkeypatch):
    _program(repo, "claude.exe")
    installed = _program(tmp_path / "bin", "claude.exe")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    assert launch_argv(["claude"], windows=True, which=_windows_which) == [str(installed)]
    assert launch_argv(["claude"], {}, windows=True, which=_windows_which) == [str(installed)]


def test_find_program_passes_over_the_current_directory(repo, tmp_path):
    _program(repo, "claude.exe")
    env = {"PATH": str(tmp_path)}
    assert find_program("claude", env, windows=True, which=_windows_which) is None
    installed = _program(tmp_path, "claude.exe")
    assert find_program("claude", env, windows=True, which=_windows_which) == str(installed)


def test_find_program_off_windows_is_shutil_which():
    calls = []

    def which(*args, **kwargs):
        calls.append((args, kwargs))
        return "/usr/bin/claude"

    assert find_program("claude", windows=False, which=which) == "/usr/bin/claude"
    assert find_program("claude", {"PATH": "/opt"}, windows=False, which=which) == "/usr/bin/claude"
    assert calls == [(("claude",), {}), (("claude",), {"path": "/opt"})]
