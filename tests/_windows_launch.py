"""Run the suite with the Windows launch rules on, from any platform.

``quodeq.shared.win_launch`` rewrites an agent CLI's argv on Windows only,
so a test that fakes the spawn of a CLI that is not installed passes on
macOS and Linux and fails on the Windows runners, where a bare name found
in no PATH directory is refused. To see those failures before CI does::

    QUODEQ_TEST_WINDOWS_LAUNCH=1 uv run pytest -q -m "not integration"

That turns the Windows branch on for the whole session. Lookups still go
through this platform's ``shutil.which``, so PATHEXT is not simulated; the
rule under test is "resolved from a PATH directory or refused".

A test that fakes a CLI spawn asks for the ``installed_cli`` fixture, which
puts stand-in programs for the agent CLIs in a directory of its own, first
on PATH. It is opt-in on purpose: an autouse version
would make every name resolvable and hide the refusal these rules exist for.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ENV_VAR = "QUODEQ_TEST_WINDOWS_LAUNCH"
# The agent CLIs, and the made-up provider name registration tests use.
STAND_IN_CLIS = ("claude", "codex", "gemini", "copilot", "agy", "mycli")
WINDOWS_SYSTEM_TOOLS = ("cmd", "powershell", "taskkill")
_WIN_LAUNCH_IS_WIN32 = "quodeq.shared.win_launch.IS_WIN32"


@pytest.fixture(scope="session", autouse=True)
def _windows_launch_rules() -> Iterator[None]:
    """Turn the Windows launch branch on for the session when ENV_VAR is 1."""
    if os.environ.get(ENV_VAR) != "1":
        yield
        return
    patcher = pytest.MonkeyPatch()
    patcher.setattr(_WIN_LAUNCH_IS_WIN32, True)
    if sys.platform != "win32":
        # Helper programs (git, gh...) have no .exe here: look them up by their own name.
        patcher.setattr("quodeq.shared.win_launch._EXE", "")
    yield
    patcher.undo()


def _stand_ins(bin_dir: Path, names: tuple[str, ...], monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put an empty program (and its .exe) per name in *bin_dir*, first on PATH."""
    for name in names:
        for filename in (name, name + ".exe"):
            program = bin_dir / filename
            program.write_text("", encoding="utf-8")
            program.chmod(0o755)
    monkeypatch.setenv("PATH", os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]))
    return bin_dir


@pytest.fixture
def installed_cli(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory holding a stand-in for each agent CLI, put first on PATH.

    Returns the directory. On Windows (or with ENV_VAR set) a faked spawn
    then sees ``<directory>/<cli>[.exe]`` as argv[0] instead of the bare name.
    """
    return _stand_ins(tmp_path_factory.mktemp("installed-cli"), STAND_IN_CLIS, monkeypatch)


@pytest.fixture
def windows_system_tools(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand-ins for cmd, powershell and taskkill, for a test that fakes their spawn off Windows."""
    return _stand_ins(tmp_path_factory.mktemp("system-tools"), WINDOWS_SYSTEM_TOOLS, monkeypatch)


@pytest.fixture
def argv_as_written(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave a spawned argv as the code wrote it, on every platform.

    For a test that compares a faked spawn's argv word for word, or swaps
    ``shutil.which`` for the whole process: what it checks is the command,
    not where Windows finds the program. Opt-in per test for the same reason
    as ``installed_cli``.
    """
    monkeypatch.setattr(_WIN_LAUNCH_IS_WIN32, False)
