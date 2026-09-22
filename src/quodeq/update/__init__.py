"""Update subsystem.

Notify-only for wheel installs (pip/uv/pipx/brew own the binary there). The
frozen macOS dashboard app may self-replace via quodeq.update.selfupdate,
which verifies notarization and the pinned Team ID before swapping the bundle.
"""

from quodeq.update.checker import (
    check_async,
    dismiss,
    get_status,
    run_check,
    set_settings,
)

__all__ = ["check_async", "dismiss", "get_status", "run_check", "set_settings"]
