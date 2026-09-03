"""First-launch UX for the packaged macOS app.

When the app runs from the mounted DMG (or an App Translocation path, where it
can never self-update), offer to copy it into /Applications and relaunch from
there. Runs BEFORE the GUI loop starts, via an osascript dialog, deliberately
staying clear of the pywebview-dialog deadlock class. Fail-soft: any problem
means the app just launches normally from where it is.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from quodeq.update.selfupdate import bundle_path

_logger = logging.getLogger(__name__)

APPLICATIONS_DIR = Path("/Applications")

_DIALOG_SCRIPT = (
    'display dialog "Quodeq works best from the Applications folder. '
    'Move it there now?" buttons {"Not Now", "Move"} '
    'default button "Move" with title "Quodeq"'
)


def needs_move(bundle: Path | None) -> bool:
    """True when the app runs from the DMG or a translocated (read-only) path."""
    if bundle is None:
        return False
    path = str(bundle).replace("\\", "/")
    return path.startswith("/Volumes/") or "/AppTranslocation/" in path


def _ask_move(runner) -> bool:
    result = runner(["osascript", "-e", _DIALOG_SCRIPT], capture_output=True, text=True, encoding="utf-8")
    return result.returncode == 0 and "button returned:Move" in (result.stdout or "")


def offer_move_to_applications(
    bundle: Path | None = None,
    *,
    applications_dir: Path | None = None,
    runner=subprocess.run,
) -> bool:
    """Offer the move; True means the app relaunched elsewhere and we should exit."""
    try:
        app = bundle if bundle is not None else bundle_path()
        if not needs_move(app):
            return False
        if not _ask_move(runner):
            return False
        dest = (applications_dir or APPLICATIONS_DIR) / app.name
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        copied = runner(["ditto", str(app), str(dest)], capture_output=True, text=True, encoding="utf-8")
        if copied.returncode != 0:
            _logger.warning("move to Applications failed: %s", copied.stderr)
            return False
        runner(["open", "-n", str(dest)], capture_output=True, text=True, encoding="utf-8")
        return True
    except Exception:
        _logger.debug("move-to-Applications offer failed", exc_info=True)
        return False
