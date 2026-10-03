"""Unit tests for the move-to-Applications first-launch offer. No real dialogs."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_relaunch_failure_returns_false(tmp_path: Path) -> None:
    """A nonzero `open` returncode means the relaunch didn't actually happen:
    offer_move_to_applications must report False so the caller does not exit
    the running instance with no replacement launched."""
    app = _fake_dmg_bundle(tmp_path)
    apps_dir = tmp_path / "Applications"
    apps_dir.mkdir()
    runner = _runner()

    def failing_open_runner(argv, **kwargs):
        result = runner(argv, **kwargs)
        if Path(argv[0]).name == "open":
            result.returncode = 1
            result.stderr = "open: relaunch failed"
        return result

    failing_open_runner.calls = runner.calls
    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"),
        applications_dir=apps_dir,
        runner=_spy_fs(failing_open_runner, app),
    )
    assert moved is False
    tools = [Path(c[0]).name for c in runner.calls]
    assert tools == ["osascript", "ditto", "open"]


def test_runner_os_error_is_swallowed(tmp_path: Path) -> None:
    """A tool (osascript/ditto/open) that can't launch raises OSError."""
    def exploding_runner(argv, **kwargs):
        raise OSError("boom")

    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=tmp_path, runner=exploding_runner
    )
    assert moved is False


def test_runner_unicode_decode_error_is_swallowed(tmp_path: Path) -> None:
    """A tool whose output isn't valid UTF-8 raises UnicodeDecodeError
    (text=True, encoding="utf-8" on subprocess.run)."""
    def exploding_runner(argv, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=tmp_path, runner=exploding_runner
    )
    assert moved is False


def test_runner_out_of_scope_error_propagates(tmp_path: Path) -> None:
    """R-FT-7 — an error outside (OSError, UnicodeDecodeError) (e.g. a
    programming bug) must now propagate instead of being swallowed."""
    def exploding_runner(argv, **kwargs):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        first_launch.offer_move_to_applications(
            Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=tmp_path, runner=exploding_runner
        )


def _dmg_with_previous_install(tmp_path: Path) -> tuple[Path, Path]:
    """A DMG bundle plus an /Applications copy of an earlier install."""
    app = _fake_dmg_bundle(tmp_path)
    (app / "Contents" / "marker").write_text("new")
    apps_dir = tmp_path / "Applications"
    (apps_dir / "Quodeq.app").mkdir(parents=True)
    (apps_dir / "Quodeq.app" / "marker").write_text("previous")
    return app, apps_dir


def test_failed_copy_keeps_previous_bundle(tmp_path: Path) -> None:
    app, apps_dir = _dmg_with_previous_install(tmp_path)
    runner = _runner(ditto_rc=1)
    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=apps_dir, runner=_spy_fs(runner, app),
    )
    assert moved is False
    assert (apps_dir / "Quodeq.app" / "marker").read_text() == "previous"
    assert sorted(p.name for p in apps_dir.iterdir()) == ["Quodeq.app"]
    assert [Path(c[0]).name for c in runner.calls] == ["osascript", "ditto"]


def test_failed_rename_restores_previous_bundle(tmp_path: Path, monkeypatch) -> None:
    app, apps_dir = _dmg_with_previous_install(tmp_path)
    runner = _runner()
    real_rename = Path.rename

    def _rename(self, target):
        if self.name.endswith(".partial"):
            raise OSError(13, "Permission denied", str(self))
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", _rename)
    with patch.object(first_launch._logger, "warning") as warning:
        moved = first_launch.offer_move_to_applications(
            Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=apps_dir, runner=_spy_fs(runner, app),
        )
    assert moved is False
    assert (apps_dir / "Quodeq.app" / "marker").read_text() == "previous"
    assert sorted(p.name for p in apps_dir.iterdir()) == ["Quodeq.app"]
    assert [Path(c[0]).name for c in runner.calls] == ["osascript", "ditto"]
    assert warning.called


def test_successful_copy_replaces_previous_bundle(tmp_path: Path) -> None:
    app, apps_dir = _dmg_with_previous_install(tmp_path)
    (apps_dir / "Quodeq.app.partial").mkdir()  # leftover from an interrupted move
    runner = _runner()
    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=apps_dir, runner=_spy_fs(runner, app),
    )
    assert moved is True
    dest = apps_dir / "Quodeq.app"
    assert (dest / "Contents" / "marker").read_text() == "new"
    assert not (dest / "marker").exists()
    assert sorted(p.name for p in apps_dir.iterdir()) == ["Quodeq.app"]
    assert runner.calls[-1] == ["open", "-n", str(dest)]


def _dmg_with_bundle_left_aside(tmp_path: Path) -> tuple[Path, Path]:
    """A DMG bundle plus an earlier install left at Quodeq.app.previous, no Quodeq.app."""
    app, apps_dir = _dmg_with_previous_install(tmp_path)
    (apps_dir / "Quodeq.app").rename(apps_dir / "Quodeq.app.previous")
    return app, apps_dir


def test_bundle_left_aside_is_put_back_when_the_copy_fails(tmp_path: Path) -> None:
    app, apps_dir = _dmg_with_bundle_left_aside(tmp_path)
    runner = _runner(ditto_rc=1)
    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=apps_dir, runner=_spy_fs(runner, app),
    )
    assert moved is False
    assert (apps_dir / "Quodeq.app" / "marker").read_text() == "previous"
    assert sorted(p.name for p in apps_dir.iterdir()) == ["Quodeq.app"]


def test_bundle_left_aside_is_replaced_when_the_copy_succeeds(tmp_path: Path) -> None:
    app, apps_dir = _dmg_with_bundle_left_aside(tmp_path)
    runner = _runner()
    moved = first_launch.offer_move_to_applications(
        Path("/Volumes/Quodeq/Quodeq.app"), applications_dir=apps_dir, runner=_spy_fs(runner, app),
    )
    assert moved is True
    assert (apps_dir / "Quodeq.app" / "Contents" / "marker").read_text() == "new"
    assert sorted(p.name for p in apps_dir.iterdir()) == ["Quodeq.app"]
