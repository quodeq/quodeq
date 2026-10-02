"""Parse git's --progress stderr into a percent and a byte count.

Git prints "Receiving objects:  45% (1200/2650), 12.30 MiB | 2.10 MiB/s"
and overwrites the line with carriage returns. Only the receiving phase
carries a transfer size; counting and compressing are reported as 0 % so
the bar shows life before bytes flow, and resolving deltas as 100 % (the
download is over). Pure: no I/O, no state.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_RECEIVING = re.compile(r"^Receiving objects:\s+(?P<percent>\d+)%(?: \(\d+/\d+\))?(?:, (?P<amount>[\d.]+) (?P<unit>bytes|KiB|MiB|GiB))?")
_PRE_PHASES = ("Counting objects:", "Compressing objects:")
_POST_PHASE = "Resolving deltas:"
_UNIT = {"bytes": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3}
_PERCENT_FULL = 100
_PERCENT_NONE = 0


@dataclass(frozen=True)
class ProgressUpdate:
    """Percent complete and bytes received so far; None when unknown."""

    percent: int | None
    bytes: int | None


def parse_progress(line: str) -> ProgressUpdate | None:
    """A progress update for *line*, or None when the line carries none."""
    text = (line or "").strip()
    if not text:
        return None
    match = _RECEIVING.match(text)
    if match:
        percent = min(int(match["percent"]), _PERCENT_FULL)
        size = _size_bytes(match["amount"], match["unit"])
        return ProgressUpdate(percent, size)
    if text.startswith(_PRE_PHASES):
        return ProgressUpdate(_PERCENT_NONE, None)
    if text.startswith(_POST_PHASE):
        return ProgressUpdate(_PERCENT_FULL, None)
    return None


def _size_bytes(amount: str | None, unit: str | None) -> int | None:
    if amount is None or unit is None:
        return None
    try:
        return int(float(amount) * _UNIT[unit])
    except (ValueError, OverflowError, KeyError):
        return None
