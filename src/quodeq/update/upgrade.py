"""``quodeq upgrade``: run the upgrade command that matches how quodeq was installed.

The command comes from ``channel.upgrade_argv`` (pipx, uv tool, Homebrew, or
this interpreter's pip). The bundled desktop app has no such command; it is
pointed at the download instead.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from typing import TextIO

from quodeq import __version__
from quodeq.shared.win_launch import find_program, program_argv
from quodeq.update.channel import upgrade_argv
from quodeq.update.checker import get_status, run_check
from quodeq.update.compare import is_newer

_RELEASES_URL = "https://github.com/quodeq/quodeq/releases/latest"


def run_upgrade(
    dry_run: bool = False,
    *,
    env: dict[str, str] | None = None,
    out: TextIO | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
) -> int:
    """Upgrade this install in place and return the exit code to report.

    *run* and *which* exist for tests.
    """
    stream = out if out is not None else sys.stdout
    argv = upgrade_argv(env)
    if argv is None:
        status = get_status(env)
        url = status.get("download_url") or status.get("latest_url") or _RELEASES_URL
        print(f"This is the desktop app. Download the latest version from {url}", file=stream)
        return 1

    run_check(env, force=True)
    latest = get_status(env).get("latest")
    if latest and not is_newer(__version__, latest):
        print(f"quodeq {__version__} is the latest version.", file=stream)
        return 0

    command = " ".join(argv)
    if dry_run:
        print(f"Would run: {command}", file=stream)
        return 0
    if find_program(argv[0], which=which) is None:
        print(f"{argv[0]} isn't on your PATH. Run the upgrade yourself: {command}", file=stream)
        return 1

    target = f" to {latest}" if latest else ""
    print(f"Upgrading quodeq {__version__}{target}: {command}", file=stream, flush=True)
    try:
        code = run(program_argv(argv, which=which), check=False).returncode
    except OSError as exc:
        print(f"Could not start the upgrade ({exc}). Run it yourself: {command}", file=stream)
        return 1
    if code != 0:
        print(f"The upgrade failed (exit code {code}). See the output above.", file=stream)
        return code
    print("Upgraded. If Quodeq is open, restart it to use the new version: quodeq stop, then quodeq.", file=stream)
    return 0
