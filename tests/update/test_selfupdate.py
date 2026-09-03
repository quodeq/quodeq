"""Unit tests for the macOS self-update engine. No network, no real subprocesses."""

from __future__ import annotations

import plistlib
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.update import selfupdate

DMG_URL = "https://example.com/Quodeq-1.11.0-macOS.dmg"


@pytest.fixture(autouse=True)
def _reset_state():
    selfupdate._reset_for_tests()
    yield
    selfupdate._reset_for_tests()


def _make_bundle(root: Path, name: str = "Quodeq.app", version: str = "1.11.0") -> Path:
    app = root / name
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleShortVersionString": version})
    )
    return app


# ---------------------------------------------------------------- describe()


def _describe(tmp_path: Path, **overrides) -> dict:
    app = overrides.pop("app", None)
    if app is None:
        app = _make_bundle(tmp_path)
    kwargs = {
        "frozen": True,
        "platform": "darwin",
        "executable": str(app / "Contents" / "MacOS" / "Quodeq"),
        "team_id": "ABCDE12345",
    }
    kwargs.update(overrides)
    return selfupdate.describe(overrides.get("download_url", DMG_URL), **{
        k: v for k, v in kwargs.items() if k != "download_url"
    })


def test_describe_supported(tmp_path: Path) -> None:
    result = _describe(tmp_path)
    assert result["supported"] is True
    assert result["reason"] is None
    assert result["phase"] == "idle"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"frozen": False}, "not_frozen"),
        ({"platform": "win32"}, "not_macos"),
        ({"team_id": ""}, "no_team_id"),
        ({"executable": "/usr/local/bin/quodeq"}, "no_bundle"),
        ({"download_url": None}, "no_asset"),
        ({"download_url": "https://example.com/QuodeqBar-1.11.0-macOS.dmg"}, "no_asset"),
    ],
)
def test_describe_unsupported_reasons(tmp_path: Path, overrides: dict, reason: str) -> None:
    result = _describe(tmp_path, **overrides)
    assert result["supported"] is False
    assert result["reason"] == reason


def test_describe_translocated(tmp_path: Path) -> None:
    exe = "/private/var/folders/xy/AppTranslocation/f00/d/Quodeq.app/Contents/MacOS/Quodeq"
    result = _describe(tmp_path, executable=exe)
    assert result["supported"] is False
    assert result["reason"] == "translocated"


def test_describe_running_from_dmg_volume(tmp_path: Path) -> None:
    exe = "/Volumes/Quodeq/Quodeq.app/Contents/MacOS/Quodeq"
    result = _describe(tmp_path, executable=exe)
    assert result["supported"] is False
    assert result["reason"] == "translocated"


def test_describe_not_writable(tmp_path: Path) -> None:
    app = _make_bundle(tmp_path)
    with patch("quodeq.update.selfupdate.os.access", return_value=False):
        result = _describe(tmp_path, app=app)
    assert result["supported"] is False
    assert result["reason"] == "not_writable"


# ---------------------------------------------------------------- engine


class _FakeCommands:
    """Dispatches mocked subprocess.run calls and records them."""

    def __init__(self, mount_root: Path, app_version: str = "1.11.0",
                 team_id: str = "ABCDE12345", spctl_ok: bool = True,
                 codesign_ok: bool = True):
        self.mount_root = mount_root
        self.app_version = app_version
        self.team_id = team_id
        self.spctl_ok = spctl_ok
        self.codesign_ok = codesign_ok
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        tool = Path(argv[0]).name
        result = MagicMock(returncode=0, stdout="", stderr="")
        if tool == "spctl":
            result.returncode = 0 if self.spctl_ok else 3
        elif tool == "hdiutil" and argv[1] == "attach":
            _make_bundle(self.mount_root, version=self.app_version)
        elif tool == "codesign" and "--verify" in argv:
            result.returncode = 0 if self.codesign_ok else 1
        elif tool == "codesign" and "-dvv" in argv:
            result.stderr = f"TeamIdentifier={self.team_id}\n"
        elif tool == "ditto":
            shutil.copytree(argv[-2], argv[-1])
        return result


def _fake_download(dest: Path):
    def _download(url: str, target: Path, _progress) -> None:
        target.write_bytes(b"dmg-bytes")
    return _download


def _run_engine(tmp_path: Path, fake: _FakeCommands, target_version: str = "1.11.0"):
    install_app = _make_bundle(tmp_path / "Applications", version="1.10.1")
    exits: list[bool] = []
    with (
        patch("quodeq.update.selfupdate.subprocess.run", side_effect=fake),
        patch("quodeq.update.selfupdate.subprocess.Popen") as popen,
        patch("quodeq.update.selfupdate._download_file", _fake_download(tmp_path)),
        patch("quodeq.update.selfupdate._request_app_exit", lambda: exits.append(True)),
    ):
        started = selfupdate.start(
            DMG_URL, target_version, install_app=install_app, team_id="ABCDE12345"
        )
        assert started is True
        selfupdate._join_for_tests()
    return install_app, fake, popen, exits


def test_happy_path_swaps_bundle_and_relaunches(tmp_path: Path) -> None:
    fake = _FakeCommands(mount_root=tmp_path / "mnt-root")
    with patch("quodeq.update.selfupdate._mountpoint_for_tests", tmp_path / "mnt-root"):
        install_app, fake, popen, exits = _run_engine(tmp_path, fake)

    tools = [Path(c[0]).name + (":" + c[1] if len(c) > 1 and not c[1].startswith("-") else "")
             for c in fake.calls]
    assert any(t.startswith("spctl") for t in tools)
    assert "hdiutil:attach" in tools
    assert "hdiutil:detach" in tools
    # New bundle in place, old one gone
    version = plistlib.loads((install_app / "Contents" / "Info.plist").read_bytes())
    assert version["CFBundleShortVersionString"] == "1.11.0"
    assert not list(install_app.parent.glob(".Quodeq.app.old-*"))
    # Relaunch helper spawned detached, app exit requested
    assert popen.call_count == 1
    assert popen.call_args.kwargs.get("start_new_session") is True
    assert exits == [True]
    assert selfupdate.describe(DMG_URL)["phase"] == "relaunching"


def test_spctl_rejection_errors_without_touching_install(tmp_path: Path) -> None:
    fake = _FakeCommands(mount_root=tmp_path / "mnt-root", spctl_ok=False)
    with patch("quodeq.update.selfupdate._mountpoint_for_tests", tmp_path / "mnt-root"):
        install_app, fake, popen, exits = _run_engine(tmp_path, fake)
    status = selfupdate.describe(DMG_URL)
    assert status["phase"] == "error"
    assert status["error"]
    version = plistlib.loads((install_app / "Contents" / "Info.plist").read_bytes())
    assert version["CFBundleShortVersionString"] == "1.10.1"
    assert popen.call_count == 0 and exits == []


def test_team_id_mismatch_errors(tmp_path: Path) -> None:
    fake = _FakeCommands(mount_root=tmp_path / "mnt-root", team_id="EVIL999999")
    with patch("quodeq.update.selfupdate._mountpoint_for_tests", tmp_path / "mnt-root"):
        install_app, *_ = _run_engine(tmp_path, fake)
    assert selfupdate.describe(DMG_URL)["phase"] == "error"
    version = plistlib.loads((install_app / "Contents" / "Info.plist").read_bytes())
    assert version["CFBundleShortVersionString"] == "1.10.1"


def test_version_mismatch_errors(tmp_path: Path) -> None:
    fake = _FakeCommands(mount_root=tmp_path / "mnt-root", app_version="1.11.0")
    with patch("quodeq.update.selfupdate._mountpoint_for_tests", tmp_path / "mnt-root"):
        install_app, *_ = _run_engine(tmp_path, fake, target_version="1.12.0")
    assert selfupdate.describe(DMG_URL)["phase"] == "error"


def test_second_start_while_running_is_rejected(tmp_path: Path) -> None:
    install_app = _make_bundle(tmp_path / "Applications")
    with selfupdate._lock:
        selfupdate._progress["phase"] = "downloading"
    assert selfupdate.start(DMG_URL, "1.11.0", install_app=install_app, team_id="X") is False


def test_cleanup_stale_staging(tmp_path: Path) -> None:
    install_app = _make_bundle(tmp_path / "Applications")
    parent = install_app.parent
    (parent / ".Quodeq.app.old-123").mkdir()
    (parent / ".Quodeq.app.new").mkdir()
    (parent / "Other.app").mkdir()
    selfupdate.cleanup_stale_staging(install_app)
    assert not (parent / ".Quodeq.app.old-123").exists()
    assert not (parent / ".Quodeq.app.new").exists()
    assert (parent / "Other.app").exists()
    assert install_app.exists()
