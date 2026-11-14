"""Linux app identity: the window's app id, a launcher entry and a hicolor icon.

GNOME on Wayland ignores an icon a window sets for itself. It takes the app
id the window announces (GTK uses the program name) and shows the icon of the
``.desktop`` file with that name. A pip or pipx install has no post-install
step, so the window process writes the entry and the icon on each launch,
only when they changed, and never over an entry the user edited.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

from quodeq.shared.env_paths import get_xdg_data_home
from quodeq.shared.logging import log_debug

__all__ = ["APP_ID", "install_desktop_entry", "find_launcher", "set_linux_app_identity", "set_program_name"]

APP_ID = "quodeq"  # Wayland app id, .desktop file name and icon name
_LAUNCHER_NAME = "quodeq"  # the console script pip and pipx install
_ICON_SIZE_DIR = "256x256"  # matches the shipped icon.png
_STAMP_KEY = "X-Quodeq-Stamp"  # hash of the body Quodeq wrote; a mismatch means the user edited it
# Characters the desktop entry spec would need escaped inside Exec. A launcher
# path with any of them is skipped rather than written wrong.
_UNSAFE_EXEC_CHARS = frozenset('"`$\\%\n')


def set_program_name() -> None:
    """Make GTK announce ``quodeq`` as the window's app id.

    Must run before GTK initialises. Without it the app id is the script name,
    which no ``.desktop`` file matches, so GNOME shows a generic icon.
    """
    try:
        from gi.repository import GLib  # noqa: PLC0415
    except (ImportError, ValueError) as exc:
        log_debug(f"program name not set, no GLib: {exc}")
        return
    GLib.set_prgname(APP_ID)


def find_launcher() -> Path | None:
    """The ``quodeq`` command of this install: beside the interpreter, else on PATH."""
    beside = Path(sys.executable).parent / _LAUNCHER_NAME
    if beside.is_file():
        return beside
    found = shutil.which(_LAUNCHER_NAME)
    return Path(found) if found else None


def _stamp(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _entry_text(launcher: Path) -> str | None:
    text = str(launcher)
    if any(ch in _UNSAFE_EXEC_CHARS for ch in text):
        return None
    exec_value = f'"{text}"' if any(ch.isspace() for ch in text) else text
    body = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_ID}\n"
        "Comment=Evaluate the quality of your code\n"
        f"Exec={exec_value}\n"
        f"TryExec={text}\n"
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        "Categories=Development;\n"
        f"StartupWMClass={APP_ID}\n"
    )
    return f"{body}{_STAMP_KEY}={_stamp(body)}\n"


def _ours_unedited(existing: str) -> bool:
    """True when *existing* is an entry Quodeq wrote and nobody changed since."""
    body, sep, stamp_line = existing.rstrip("\n").rpartition("\n")
    key, eq, value = stamp_line.partition("=")
    return bool(sep and eq) and key == _STAMP_KEY and value == _stamp(body + "\n")


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _install_entry(entry_path: Path, text: str) -> bool:
    if entry_path.exists():
        existing = entry_path.read_text(encoding="utf-8", errors="replace")
        if existing == text:
            return False
        if not _ours_unedited(existing):
            log_debug(f"leaving {entry_path} alone: it was not written by Quodeq or was edited")
            return False
    _write_atomic(entry_path, text.encode("utf-8"))
    return True


def _install_icon(icon_dest: Path, icon: Path) -> bool:
    data = icon.read_bytes()
    if icon_dest.exists() and icon_dest.read_bytes() == data:
        return False
    _write_atomic(icon_dest, data)
    return True


def install_desktop_entry(data_home: Path, launcher: Path, icon: Path) -> bool:
    """Write ``quodeq.desktop`` and the hicolor icon under *data_home*.

    Returns True when anything was written. Idempotent: unchanged files are
    not touched, and an entry the user edited (or wrote) is kept as it is.
    """
    text = _entry_text(launcher)
    if text is None:
        log_debug(f"launcher entry skipped: unsupported characters in {launcher}")
        return False
    icon_dest = data_home / "icons" / "hicolor" / _ICON_SIZE_DIR / "apps" / f"{APP_ID}.png"
    wrote_icon = _install_icon(icon_dest, icon)
    wrote_entry = _install_entry(data_home / "applications" / f"{APP_ID}.desktop", text)
    return wrote_icon or wrote_entry


def set_linux_app_identity(icon: str | None) -> None:
    """Set the app id and make sure GNOME has an entry and icon to match it."""
    set_program_name()
    launcher = find_launcher()
    if not icon or launcher is None:
        log_debug("launcher entry skipped: no icon or no quodeq command found")
        return
    try:
        install_desktop_entry(get_xdg_data_home(), launcher, Path(icon))
    except OSError as exc:
        log_debug(f"launcher entry not written: {exc}")
