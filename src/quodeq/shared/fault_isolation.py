"""One shared fault-isolation boundary for entry points.

Use it only where a failure must not take down the caller: a thread or task
entry point, one iteration of an event loop or work queue, or a callback the
host invokes on code it does not own. Everywhere else, catch the specific
exceptions the code can raise. ``tools/check_fault_tolerance.py`` flags a
call that is not at an entry point.
"""
from __future__ import annotations

import logging
import traceback
from typing import Callable, Protocol, TypeVar

T = TypeVar("T")


class Warns(Protocol):
    """Anything with a one-string ``warning``: a LogSink or a stdlib logger."""

    def warning(self, message: str, /) -> None:
        """Report the failed *fn*'s label and traceback."""
        ...


def run_isolated(
    fn: Callable[[], T],
    *,
    label: str,
    log: Warns,
    on_error: Callable[[Exception], T] | None = None,
) -> T | None:
    """Run *fn*; on an ``Exception`` log it with the traceback and carry on.

    Returns ``fn()``'s result, or ``on_error(exc)`` (``None`` without one)
    after a failure. ``KeyboardInterrupt`` and ``SystemExit`` propagate.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 -- the one sanctioned fault-isolation boundary
        if isinstance(log, logging.Logger):
            log.warning("%s failed", label, exc_info=True)
        else:
            log.warning(f"{label} failed\n{traceback.format_exc()}")
        return on_error(exc) if on_error is not None else None
