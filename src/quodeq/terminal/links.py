"""Path resolution and editor launching for clickable terminal links.

Pure, dependency-injected helpers so the HTTP layer (api/terminal_routes.py)
stays thin and this logic is unit-testable without a PTY, a real filesystem, or
a real ``$PATH``. Three concerns:

* ``child_cwd`` — the live working directory of the PTY's shell, so a relative
  path printed by ``ls``/``grep``/pytest resolves the way the user sees it. The
  shell starts at ``$HOME`` and the user ``cd``s around, so a fixed base is
  wrong; the shell's own cwd is the correct primary base.
* ``resolve_path`` — turn a candidate token into an absolute path + existence.
* ``detect_editor`` / ``build_open_argv`` — pick an editor and build its argv.

Nothing here raises into a request: callers treat ``None``/``False`` as "no
link" / "didn't open".
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from quodeq.shared.constants import PLATFORM_DARWIN, PLATFORM_WIN32

# Well-known CLI locations to probe IN ADDITION to $PATH. A macOS app launched
# from Finder/Dock inherits a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin) that
# usually lacks `code`/`cursor`, so a PATH-only lookup would silently fall back
# to `open` and lose the line jump. These cover Homebrew and the CLI shipped
# inside the app bundle.
_CODE_CANDIDATES = (
    "/opt/homebrew/bin/code",
    "/usr/local/bin/code",
    "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code",
)
_CURSOR_CANDIDATES = (
    "/opt/homebrew/bin/cursor",
    "/usr/local/bin/cursor",
    "/Applications/Cursor.app/Contents/Resources/app/bin/cursor",
)
_EDITOR_STARTFILE = "startfile"  # Windows os.startfile sentinel: no argv form


@dataclass(frozen=True)
class Editor:
    """A resolved editor launcher.

    ``name`` is a stable identifier surfaced to the client (telemetry / "opened
    in X"). ``path`` is the executable (or the string ``"startfile"`` sentinel
    on Windows, where launching goes through ``os.startfile`` rather than argv).
    ``supports_line`` is True only for editors we can send a ``file:line:col``
    goto to (VS Code / Cursor via ``-g``).
    """

    name: str
    path: str
    supports_line: bool


def child_cwd(
    pid: int | None,
    *,
    platform: str = sys.platform,
    readlink=os.readlink,
    run=subprocess.run,
) -> str | None:
    """Best-effort live cwd of the shell process ``pid`` (None if unknown).

    Linux exposes it as ``/proc/<pid>/cwd``; macOS has no ``/proc`` so we shell
    out to ``lsof`` (bounded, best-effort). Any failure returns None so the
    caller falls back to other bases.
    """
    if not pid:
        return None
    try:
        if platform.startswith("linux"):
            return readlink(f"/proc/{pid}/cwd")
        if platform == PLATFORM_DARWIN:
            # -Fn = machine-readable, one field per line; the cwd path is the
            # 'n'-prefixed line of the 'cwd' fd record.
            proc = run(
                ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                capture_output=True, text=True, timeout=2,
            )
            for line in proc.stdout.splitlines():
                if line.startswith("n"):
                    return line[1:]
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def resolve_bases(pid: int | None, *, getcwd=os.getcwd, home=None) -> list[str]:
    """Ordered bases for resolving a relative token: shell cwd, then the server's
    launch dir, then home. Deduped, preserving order."""
    home = home if home is not None else os.path.expanduser("~")
    ordered = [child_cwd(pid), _safe(getcwd), home]
    seen: set[str] = set()
    out: list[str] = []
    for b in ordered:
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def _safe(fn):
    try:
        return fn()
    except OSError:
        return None


def safe_editor_path(
    path: str,
    bases: list[str],
    *,
    realpath=os.path.realpath,
    commonpath=os.path.commonpath,
) -> str | None:
    """Return the canonical real path of ``path`` iff it lives under one of the
    terminal's working directories (``bases``); otherwise None.

    Guards the /open launch: the client may send any path, but we only ever hand
    the editor a file inside the directories the terminal actually operates in
    (shell cwd, server cwd, home). This both bounds the blast radius and, because
    the launch sinks consume the *returned* normalized value, sanitizes the
    untrusted input (a symlink escaping a base resolves out via realpath and is
    rejected).
    """
    # A NUL byte can never appear in a real path. Reject it up front: POSIX
    # realpath raises ValueError on it, but Windows realpath returns it intact,
    # so an explicit guard is what makes the behavior consistent and keeps the
    # NUL out of the editor launch on every platform.
    if "\x00" in path:
        return None
    try:
        real = realpath(path)
    except (OSError, ValueError):
        return None
    for base in bases:
        try:
            base_real = realpath(base)
        except (OSError, ValueError):
            continue
        try:
            if commonpath([real, base_real]) == base_real:
                return real
        except ValueError:  # mixed abs/rel or different drive (Windows)
            continue
    return None


@dataclass(frozen=True, slots=True)
class PathOps:
    """The ``os.path`` functions ``resolve_path`` relies on, injectable for tests."""

    isabs: Callable[[str], bool] = os.path.isabs
    isfile: Callable[[str], bool] = os.path.isfile
    join: Callable[..., str] = os.path.join
    normpath: Callable[[str], str] = os.path.normpath
    expanduser: Callable[[str], str] = os.path.expanduser


_OS_PATH_OPS = PathOps()


def resolve_path(token: str, bases: list[str], *, ops: PathOps = _OS_PATH_OPS) -> tuple[str, bool]:
    """Resolve a candidate path token to ``(abs_path, exists)``.

    Absolute (incl. ``~``) tokens are used as-is. Relative tokens are tried
    against each base in order; the first that is a regular file wins. When none
    exist, the first base is used so the client still gets a canonical path
    (with ``exists=False``, so it never becomes a link).
    """
    token = ops.expanduser(token)
    if ops.isabs(token):
        p = ops.normpath(token)
        return p, ops.isfile(p)
    for base in bases:
        cand = ops.normpath(ops.join(base, token))
        if ops.isfile(cand):
            return cand, True
    fallback = ops.normpath(ops.join(bases[0], token)) if bases else token
    return fallback, False


def detect_editor(
    *,
    which=shutil.which,
    isfile=os.path.isfile,
    platform: str = sys.platform,
) -> Editor | None:
    """Pick an editor: VS Code, then Cursor (PATH + known locations), then the
    OS default opener. None only on a platform with no opener at all."""
    for name, candidates in (("code", _CODE_CANDIDATES), ("cursor", _CURSOR_CANDIDATES)):
        found = which(name) or next((c for c in candidates if isfile(c)), None)
        if found:
            return Editor(name=name, path=found, supports_line=True)
    if platform == PLATFORM_DARWIN:
        return Editor(name="open", path=which("open") or "/usr/bin/open", supports_line=False)
    if platform == PLATFORM_WIN32:
        # No argv — the caller routes this to os.startfile.
        return Editor(name=_EDITOR_STARTFILE, path=_EDITOR_STARTFILE, supports_line=False)
    opener = which("xdg-open")
    if opener:
        return Editor(name="xdg-open", path=opener, supports_line=False)
    return None


def build_open_argv(
    editor: Editor, path: str, line: int | None = None, col: int | None = None
) -> list[str] | None:
    """argv to launch ``editor`` on ``path`` (at ``line[:col]`` when supported).

    Returns None for the Windows ``startfile`` sentinel, which has no argv form.
    """
    if editor.name == _EDITOR_STARTFILE:
        return None
    if editor.supports_line:
        target = path
        if line:
            target += f":{line}"
            if col:
                target += f":{col}"
        return [editor.path, "-g", target]
    return [editor.path, path]
