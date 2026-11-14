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
"""
from __future__ import annotations

import re
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path

from quodeq.shared.utils import IS_WIN32

_BATCH_SUFFIXES = (".cmd", ".bat")
_NODE = "node"
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
    cmd.exe would act on.
    """
    if not (IS_WIN32 if windows is None else windows) or not argv:
        return argv
    which = which or shutil.which
    path = env.get("PATH") if env is not None else None
    found = which(argv[0], path=path)
    if found is None:
        return argv
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
    node = str(local_node) if local_node.is_file() else which(_NODE, path=path)
    return [node, str(script)] if node else None
