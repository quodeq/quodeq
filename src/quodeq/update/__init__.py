"""Update-notification subsystem (notify-only; never self-replaces the binary)."""

from quodeq.update.checker import (
    check_async,
    dismiss,
    get_status,
    run_check,
    set_settings,
)

__all__ = ["check_async", "dismiss", "get_status", "run_check", "set_settings"]
