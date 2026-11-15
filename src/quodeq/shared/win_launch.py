"""Launch npm-installed agent CLIs on Windows without cmd.exe.

npm installs ``codex``, ``gemini`` and ``copilot`` on Windows as ``.cmd``
shims. CreateProcess runs a batch file through cmd.exe, which reads ``&``,
``|``, ``>``, ``<``, ``^``, ``%`` and ``"`` in every argument, so a scan
prompt or a repo path holding them would be cut short or run commands
outside the agent's sandbox (the BatBadBut class; quoting cannot fix it,
since cmd.exe expands ``%VAR%`` inside quotes and knows no ``\\"`` escape).

:func:`launch_argv` reads the shim for the node script it starts and spawns
``node <script> args...`` instead. A shim it cannot read still runs, but
only when no argument holds a character cmd.exe would act on.

A bare command name is looked up in the PATH directories only. Windows
(``shutil.which`` and CreateProcess alike) also tries the current directory,
which during a scan is the repository being analysed, so a ``claude.exe`` or
``node.exe`` committed there would run in place of the installed one.
"""
from __future__ import annotations

import errno
import os
import re
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path

from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.utils import IS_WIN32

_BATCH_SUFFIXES = (".cmd", ".bat")
_NODE = "node"
_EXE = ".exe"
_SYSTEM_DIR = "System32"
_NODE_EXE = "node.exe"
# npm's cmd-shim ends with `"%dp0%\node_modules\<pkg>\bin\cli.js" %*`
# (older versions: `"%~dp0\node_modules\...\cli.js" %*`).
_SHIM_TARGET_RE = re.compile(r'"%~?dp0%?\\?([^"%]+)"\s+%\*')
# The shim picks node as its program; a shim for a sh or python script does not.
_NODE_PROGRAM_RE = re.compile(r"\bnode(\.exe)?\b", re.IGNORECASE)
_CMD_METACHARS = frozenset('"&|<>^%!()\r\n')


class UnsafeShimArgs(OSError):
    """A batch-file launch whose arguments cmd.exe would reinterpret."""


def launch_argv(
    argv: list[str], env: Mapping[str, str] | None = None, *,
    windows: bool | None = None, which: Callable[..., str | None] | None = None,
) -> list[str]:
    """*argv* as it can be spawned safely without a shell.

    Off Windows *argv* is returned as is. On Windows a real executable is
    resolved to its full path (CreateProcess only tries ``.exe``) and an
    npm ``.cmd`` shim becomes ``node <script>``. Raises
    :class:`UnsafeShimArgs` for any other batch file given an argument
    cmd.exe would act on, and :class:`FileNotFoundError` for a bare name
    that is in no PATH directory (see :func:`find_program`).
    """
    if not (IS_WIN32 if windows is None else windows) or not argv:
        return argv
    which = which or shutil.which
    path = env.get("PATH") if env is not None else None
    found = _find_on_path(argv[0], path, which)
    if found is None:
        if os.path.dirname(argv[0]):
            return argv  # an explicit path: the spawn reports what is wrong with it
        # A bare name handed on would have CreateProcess try the current directory.
        raise FileNotFoundError(errno.ENOENT, f"'{argv[0]}' was not found on PATH", argv[0])
    if not found.lower().endswith(_BATCH_SUFFIXES):
        return [found, *argv[1:]]
    if (node_argv := _node_argv(Path(found), path, which)) is not None:
        return [*node_argv, *argv[1:]]
    if unsafe := [arg for arg in argv[1:] if _CMD_METACHARS.intersection(arg)]:
        raise UnsafeShimArgs(
            f"{Path(found).name} is a batch file but not an npm shim, and "
            f"{len(unsafe)} of its arguments hold characters cmd.exe would run. "
            "Point AI_CMD_PATH at the CLI's .exe instead")
    return [found, *argv[1:]]


def program_argv(
    argv: list[str], env: Mapping[str, str] | None = None, *,
    windows: bool | None = None, which: Callable[..., str | None] | None = None,
) -> list[str]:
    """*argv* for a helper program (git, gh, taskkill...) spawned without a shell.

    Off Windows, and for a program given with a directory part, *argv* is
    returned as is. On Windows a bare name becomes the full path of its
    ``.exe`` (the only extension CreateProcess adds), looked up in the PATH
    directories of *env* (this process when None) and then in the Windows
    system directory, never in the current directory. Raises
    :class:`FileNotFoundError`, as the spawn does for a missing program.
    """
    if not (IS_WIN32 if windows is None else windows) or not argv or os.path.dirname(argv[0]):
        return argv
    which = which or shutil.which
    environ = resolve_env(env)
    name = argv[0] if os.path.splitext(argv[0])[1] else argv[0] + _EXE
    found = _find_on_path(name, environ.get("PATH", ""), which)
    if found is None and (system_root := environ.get("SystemRoot")):
        found = which(os.path.join(system_root, _SYSTEM_DIR, name))
    if found is None:
        raise FileNotFoundError(errno.ENOENT, f"'{argv[0]}' was not found on PATH", argv[0])
    return [found, *argv[1:]]


def find_program(
    name: str, env: Mapping[str, str] | None = None, *,
    windows: bool | None = None, which: Callable[..., str | None] | None = None,
) -> str | None:
    """Where *name* is installed, or None: ``shutil.which`` on the PATH of
    *env* (this process's when it has none), minus the current directory
    Windows adds in front. That directory counts only as a PATH entry."""
    which = which or shutil.which
    path = env.get("PATH") if env is not None else None
    if IS_WIN32 if windows is None else windows:
        return _find_on_path(name, path, which)
    return which(name) if path is None else which(name, path=path)


def _find_on_path(name: str, path: str | None, which: Callable[..., str | None]) -> str | None:
    """*name* in the first PATH directory holding it. ``which`` is asked
    about one directory at a time, by full path: only a bare name makes it
    (and CreateProcess) add the current directory. PATHEXT still applies."""
    if os.path.dirname(name):
        return which(name)
    if path is None:
        path = resolve_env().get("PATH", "")  # not os.defpath: on Windows it starts with "."
    for entry in path.split(os.pathsep):
        if entry and (found := which(os.path.join(entry, name))):
            return found
    return None


def _node_argv(shim: Path, path: str | None, which: Callable[..., str | None]) -> list[str] | None:
    """``[node, script]`` for an npm cmd-shim, or None when *shim* is not one."""
    try:
        text = shim.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = _SHIM_TARGET_RE.search(text)
    if match is None or not _NODE_PROGRAM_RE.search(text):
        return None
    script = shim.parent.joinpath(*match.group(1).split("\\"))
    if not script.is_file():
        return None
    local_node = shim.parent / _NODE_EXE
    node = str(local_node) if local_node.is_file() else _find_on_path(_NODE, path, which)
    return [node, str(script)] if node else None
