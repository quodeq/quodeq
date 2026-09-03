"""Unit tests for the move-to-Applications first-launch offer. No real dialogs."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quodeq.update import first_launch


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/Volumes/Quodeq/Quodeq.app", True),
        ("/private/var/folders/xy/AppTranslocation/f00/d/Quodeq.app", True),
        ("/Applications/Quodeq.app", False),
        (None, False),
    ],
)
def test_needs_move(path: str | None, expected: bool) -> None:
    bundle = Path(path) if path else None
    assert first_launch.needs_move(bundle) is expected


def _runner(answer: str = "button returned:Move", ditto_rc: int = 0):
    def run(argv, **kwargs):
        result = MagicMock(returncode=0, stdout="", stderr="")
        tool = Path(argv[0]).name
        if tool == "osascript":
            result.stdout = answer
        elif tool == "ditto":
            result.returncode = ditto_rc
            if ditto_rc == 0:
                shutil.copytree(argv[-2], argv[-1])
        run.calls.append(list(argv))
        return result

    run.calls = []
    return run


def _fake_dmg_bundle(tmp_path: Path) -> Path:
    # Simulated /Volumes path: needs_move keys off the string, not the fs.
    app = tmp_path / "Volumes" / "Quodeq" / "Quodeq.app"
    (app / "Contents").mkdir(parents=True)
    return Path("/Volumes/Quodeq/Quodeq.app".replace("/Volumes", str(tmp_path / "Volumes")))


def test_move_accepted_copies_and_relaunches(tmp_path: Path) -> None:
    app = _fake_dmg_bundle(tmp_path)
    apps_dir = tmp_path / "Applications"
    apps_dir.mkdir()
    runner = _runner()
    # Force needs_move: pass a /Volumes-looking bundle via monkeypatched check.
    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=apps_dir, runner=_spy_fs(runner, app)
    )
    assert moved is True
    tools = [Path(c[0]).name for c in runner.calls]
    assert tools == ["osascript", "ditto", "open"]


def _spy_fs(runner, real_app: Path):
    # ditto's source arg is the /Volumes path; redirect it to the tmp copy so
    # copytree works in tests. Compare normalized: Windows str(Path) backslashes.
    def run(argv, **kwargs):
        argv = [
            str(real_app) if str(a).replace("\\", "/") == "/Volumes/Quodeq/Quodeq.app" else a
            for a in argv
        ]
        return runner(argv, **kwargs)

    run.calls = runner.calls
    return run


def test_not_now_continues(tmp_path: Path) -> None:
    runner = _runner(answer="button returned:Not Now")
    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=tmp_path, runner=runner
    )
    assert moved is False
    assert [Path(c[0]).name for c in runner.calls] == ["osascript"]


def test_copy_failure_continues(tmp_path: Path) -> None:
    runner = _runner(ditto_rc=1)
    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=tmp_path, runner=runner
    )
    assert moved is False
    assert [Path(c[0]).name for c in runner.calls] == ["osascript", "ditto"]


def test_normal_install_never_prompts(tmp_path: Path) -> None:
    runner = _runner()
    moved = first_launch.offer_move_to_applications(
        Path("/Applications/Quodeq.app"), applications_dir=tmp_path, runner=runner
    )
    assert moved is False
    assert runner.calls == []


def test_any_exception_is_swallowed(tmp_path: Path) -> None:
    def exploding_runner(argv, **kwargs):
        raise RuntimeError("boom")

    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=tmp_path, runner=exploding_runner
    )
    assert moved is False
