"""launch_argv: npm .cmd shims spawn as `node <script>`, never through cmd.exe."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.shared import win_launch
from quodeq.shared.win_launch import UnsafeShimArgs, launch_argv

# What npm 10 writes for `npm install -g @openai/codex` (C:\...\npm\codex.cmd).
_NPM_SHIM = r"""@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0

IF EXIST "%dp0%\node.exe" (
  SET "_prog=%dp0%\node.exe"
) ELSE (
  SET "_prog=node"
  SET PATHEXT=%PATHEXT:;.JS;=;%
)

endLocal & goto #_undefined_# 2>NUL || title %COMSPEC% & "%_prog%"  "%dp0%\node_modules\@openai\codex\bin\codex.js" %*
"""
# The shape older npm (cmd-shim < 4) wrote.
_OLD_NPM_SHIM = r"""@IF EXIST "%~dp0\node.exe" (
  "%~dp0\node.exe"  "%~dp0\node_modules\@google\gemini-cli\dist\index.js" %*
) ELSE (
  @SETLOCAL
  @SET PATHEXT=%PATHEXT:;.JS;=;%
  node  "%~dp0\node_modules\@google\gemini-cli\dist\index.js" %*
)
"""
_PROMPT = 'Review "x" & calc.exe | more > out %PATH% ^'
_NODE = "/opt/node/node.exe"


def _shim(tmp_path: Path, name: str, text: str, script: str | None) -> Path:
    shim = tmp_path / name
    shim.write_text(text, encoding="utf-8")
    if script:
        target = tmp_path.joinpath(*script.split("\\"))
        target.parent.mkdir(parents=True)
        target.write_text("// cli", encoding="utf-8")
    return shim


def _which(found: dict[str, str]):
    return lambda name, path=None: found.get(name)


def test_off_windows_argv_is_untouched():
    argv = ["codex", "exec", _PROMPT]
    assert launch_argv(argv, windows=False, which=_which({})) is argv


def test_npm_shim_runs_its_script_under_node(tmp_path):
    shim = _shim(tmp_path, "codex.cmd", _NPM_SHIM, r"node_modules\@openai\codex\bin\codex.js")
    argv = launch_argv(["codex", "exec", _PROMPT], windows=True,
                       which=_which({"codex": str(shim), "node": _NODE}))
    script = tmp_path / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    assert argv == [_NODE, str(script), "exec", _PROMPT]


def test_old_npm_shim_prefers_the_node_beside_it(tmp_path):
    shim = _shim(tmp_path, "gemini.cmd", _OLD_NPM_SHIM, r"node_modules\@google\gemini-cli\dist\index.js")
    (tmp_path / "node.exe").write_text("", encoding="utf-8")
    argv = launch_argv(["gemini", "-p", _PROMPT], windows=True, which=_which({"gemini": str(shim)}))
    assert argv[0] == str(tmp_path / "node.exe")
    assert argv[1:] == [str(tmp_path / "node_modules" / "@google" / "gemini-cli" / "dist" / "index.js"),
                        "-p", _PROMPT]


def test_path_comes_from_the_child_env(tmp_path):
    seen = []
    shim = _shim(tmp_path, "codex.cmd", _NPM_SHIM, r"node_modules\@openai\codex\bin\codex.js")

    def which(name, path=None):
        seen.append(path)
        return {"codex": str(shim), "node": _NODE}[name]

    launch_argv(["codex"], {"PATH": r"C:\npm"}, windows=True, which=which)
    assert seen == [r"C:\npm", r"C:\npm"]


def test_an_exe_resolves_to_its_full_path():
    argv = launch_argv(["claude", "-p", _PROMPT], windows=True,
                       which=_which({"claude": r"C:\bin\claude.exe"}))
    assert argv == [r"C:\bin\claude.exe", "-p", _PROMPT]


def test_unknown_program_is_left_for_the_spawn_to_report():
    argv = ["codex", "--version"]
    assert launch_argv(argv, windows=True, which=_which({})) is argv


@pytest.mark.parametrize("text, script", [
    ("@echo off\r\nC:\\tools\\codex.exe %*\r\n", None),  # not an npm shim
    (_NPM_SHIM, None),  # the script it names is gone
    ('@echo off\r\n"%~dp0\\sh.exe" "%~dp0\\node_modules\\x\\cli.sh" %*\r\n',
     r"node_modules\x\cli.sh"),  # a shim for a non-node program
])
def test_unreadable_shim_falls_back_to_it_for_safe_args(tmp_path, text, script):
    shim = _shim(tmp_path, "codex.cmd", text, script)
    argv = launch_argv(["codex", "--version"], windows=True, which=_which({"codex": str(shim)}))
    assert argv == [str(shim), "--version"]


def test_unreadable_shim_refuses_args_cmd_would_run(tmp_path):
    shim = _shim(tmp_path, "codex.bat", "@echo off\r\nC:\\tools\\codex.exe %*\r\n", None)
    with pytest.raises(UnsafeShimArgs):
        launch_argv(["codex", "exec", _PROMPT], windows=True, which=_which({"codex": str(shim)}))


def test_shim_without_node_on_path_falls_back(tmp_path):
    shim = _shim(tmp_path, "codex.cmd", _NPM_SHIM, r"node_modules\@openai\codex\bin\codex.js")
    with pytest.raises(UnsafeShimArgs):
        launch_argv(["codex", "exec", _PROMPT], windows=True, which=_which({"codex": str(shim)}))


def test_default_platform_reads_is_win32(monkeypatch):
    monkeypatch.setattr(win_launch, "IS_WIN32", False)
    argv = ["codex"]
    assert launch_argv(argv) is argv
