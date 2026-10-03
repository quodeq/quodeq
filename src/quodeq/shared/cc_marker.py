"""Decode the ``_cc`` structured marker protocol.

Counterpart of ``analysis/runner_markers.py``'s ``emit_marker``, which prints
one JSON object per line keyed by ``CC_MARKER_KEY``. Lives in ``shared``
(not ``analysis``) because the reader, ``services/_job_monitor_mixin.py``,
may not import ``analysis``; both sides already share the phase vocabulary
from ``shared.constants`` for the same reason.
"""
from __future__ import annotations

import json
from typing import Any


def parse_cc_marker(line: str) -> dict[str, Any] | None:
    """Parse one ``_cc`` marker line into its JSON object.

    Returns None for malformed JSON or a JSON value that is not an object
    (a line ``emit_marker`` never produces, but a defensive reader must not
    crash on).
    """
    try:
        marker = json.loads(line)
    except json.JSONDecodeError:
        return None
    return marker if isinstance(marker, dict) else None
