"""Tell the page when the native window stops being visible.

pywebview leaves ``document.visibilityState`` on 'visible' while the window
is minimised, so the frontend's polls would otherwise keep running against a
window nobody can see. The window's minimised/restored/shown events are the
only signal, and this module forwards them into the page as the
APP_VISIBILITY_EVENT the frontend listens for (see ui/src/constants.js and
ui/src/utils/appVisibility.js).
"""
from __future__ import annotations

import json
import logging

_logger = logging.getLogger(__name__)

VISIBILITY_EVENT = "quodeq:visibility"


def visibility_js(hidden: bool) -> str:
    """The dispatch snippet for one visibility change."""
    detail = json.dumps({"hidden": bool(hidden)})
    return (
        f"window.dispatchEvent(new CustomEvent({json.dumps(VISIBILITY_EVENT)},"
        f" {{ detail: {detail} }}));"
    )


def dispatch_visibility(window: object, hidden: bool) -> None:
    """Best effort: a window that is gone or not yet loaded just misses the event."""
    try:
        window.evaluate_js(visibility_js(hidden))
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
        _logger.debug("visibility event not delivered (hidden=%s): %s", hidden, exc)


def install_visibility_events(window: object) -> None:
    """Forward minimise/restore/show to the page."""
    window.events.minimized += lambda: dispatch_visibility(window, True)
    window.events.restored += lambda: dispatch_visibility(window, False)
    window.events.shown += lambda: dispatch_visibility(window, False)
