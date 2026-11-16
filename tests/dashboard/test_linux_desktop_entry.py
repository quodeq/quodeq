"""Linux launcher entry and icon: what GNOME needs to show Quodeq's icon in the dock."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from quodeq.dashboard import linux_desktop_entry as lde
from quodeq.shared.env_paths import get_xdg_data_home

# Linux-only feature; Windows paths have backslashes and no rooted "/x" form.
pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths only")

_ICON_BYTES = b"\x89PNG fake icon"


@pytest.fixture
def icon(tmp_path: Path) -> Path:
    p = tmp_path / "src-icon.png"
    p.write_bytes(_ICON_BYTES)
    return p


def _entry(data_home: Path) -> Path:
    return data_home / "applications" / "quodeq.desktop"


def _fields(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def test_writes_entry_and_icon(tmp_path: Path, icon: Path) -> None:
    home = tmp_path / "share"
    launcher = Path("/opt/venv/bin/quodeq")
    assert lde.install_desktop_entry(home, launcher, icon) is True
    fields = _fields(_entry(home).read_text(encoding="utf-8"))
    assert fields["Exec"] == fields["TryExec"] == str(launcher)
    assert fields["Icon"] == fields["StartupWMClass"] == "quodeq"
    assert "NoDisplay" not in fields  # a visible entry the user can pin
    assert (home / "icons/hicolor/256x256/apps/quodeq.png").read_bytes() == _ICON_BYTES


def test_second_run_writes_nothing(tmp_path: Path, icon: Path) -> None:
    home = tmp_path / "share"
    launcher = Path("/opt/venv/bin/quodeq")
    lde.install_desktop_entry(home, launcher, icon)
    assert lde.install_desktop_entry(home, launcher, icon) is False


def test_rewrites_its_own_entry_when_the_launcher_moves(tmp_path: Path, icon: Path) -> None:
    home = tmp_path / "share"
    lde.install_desktop_entry(home, Path("/old/bin/quodeq"), icon)
    assert lde.install_desktop_entry(home, Path("/new/bin/quodeq"), icon) is True
    assert _fields(_entry(home).read_text(encoding="utf-8"))["Exec"] == "/new/bin/quodeq"


def test_keeps_an_entry_the_user_edited(tmp_path: Path, icon: Path) -> None:
    home = tmp_path / "share"
    lde.install_desktop_entry(home, Path("/old/bin/quodeq"), icon)
    edited = _entry(home).read_text(encoding="utf-8").replace("Terminal=false", "Terminal=true")
    _entry(home).write_text(edited, encoding="utf-8")
    lde.install_desktop_entry(home, Path("/new/bin/quodeq"), icon)
    assert _entry(home).read_text(encoding="utf-8") == edited


def test_keeps_an_entry_quodeq_did_not_write(tmp_path: Path, icon: Path) -> None:
    home = tmp_path / "share"
    _entry(home).parent.mkdir(parents=True)
    _entry(home).write_text("[Desktop Entry]\nName=mine\n", encoding="utf-8")
    lde.install_desktop_entry(home, Path("/opt/bin/quodeq"), icon)
    assert _entry(home).read_text(encoding="utf-8") == "[Desktop Entry]\nName=mine\n"


def test_quotes_a_launcher_path_with_spaces(tmp_path: Path, icon: Path) -> None:
    home = tmp_path / "share"
    lde.install_desktop_entry(home, Path("/home/a b/bin/quodeq"), icon)
    fields = _fields(_entry(home).read_text(encoding="utf-8"))
    assert fields["Exec"] == '"/home/a b/bin/quodeq"'
    assert fields["TryExec"] == "/home/a b/bin/quodeq"


def test_skips_a_launcher_path_it_cannot_escape(tmp_path: Path, icon: Path) -> None:
    home = tmp_path / "share"
    assert lde.install_desktop_entry(home, Path("/home/100%/bin/quodeq"), icon) is False
    assert not _entry(home).exists()


def test_set_program_name_sets_the_glib_prgname(monkeypatch) -> None:
    names: list[str] = []
    glib = types.SimpleNamespace(set_prgname=names.append)
    monkeypatch.setitem(sys.modules, "gi", types.ModuleType("gi"))
    monkeypatch.setitem(sys.modules, "gi.repository", types.SimpleNamespace(GLib=glib))
    lde.set_program_name()
    assert names == ["quodeq"]


def test_identity_writes_under_xdg_data_home(monkeypatch, tmp_path: Path, icon: Path) -> None:
    monkeypatch.setattr(lde, "set_program_name", lambda: None)
    monkeypatch.setattr(lde, "find_launcher", lambda: Path("/opt/bin/quodeq"))
    monkeypatch.setattr(lde, "get_xdg_data_home", lambda: tmp_path / "xdg")
    lde.set_linux_app_identity(str(icon))
    assert _entry(tmp_path / "xdg").is_file()


def test_identity_logs_and_survives_a_write_error(monkeypatch, tmp_path: Path, icon: Path) -> None:
    monkeypatch.setattr(lde, "set_program_name", lambda: None)
    monkeypatch.setattr(lde, "find_launcher", lambda: Path("/opt/bin/quodeq"))
    blocker = tmp_path / "file"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(lde, "get_xdg_data_home", lambda: blocker)
    messages: list[str] = []
    monkeypatch.setattr(lde, "log_debug", messages.append)
    lde.set_linux_app_identity(str(icon))
    assert any("launcher entry not written" in m for m in messages)


@pytest.mark.parametrize(("env", "expected"), [
    ({"XDG_DATA_HOME": "/data/x"}, Path("/data/x")),
    ({"XDG_DATA_HOME": "relative/x"}, None),
    ({}, None),
])
def test_xdg_data_home(env: dict[str, str], expected: Path | None) -> None:
    assert get_xdg_data_home(env) == (expected or Path.home() / ".local" / "share")
