"""Parse git's --progress stderr into a phase, a percent and a byte count.

Git prints "Receiving objects:  45% (1200/2650), 12.30 MiB | 2.10 MiB/s"
and overwrites the line with carriage returns. Only the receiving phase
carries a transfer size; counting and compressing are reported as the
download at 0 % so the bar shows life before bytes flow. "Resolving
deltas" and the checkout ("Updating files", "Checking out files" on older
git) are their own phases with their own percent, so a bar never sits at
100 % while git still works. Pure: no I/O, no state.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from quodeq.core.types.sync_phase import SyncPhase

_RECEIVING = re.compile(r"^Receiving objects:\s+(?P<percent>\d+)%(?: \(\d+/\d+\))?(?:, (?P<amount>[\d.]+) (?P<unit>bytes|KiB|MiB|GiB))?")
_RESOLVING = re.compile(r"^Resolving deltas:\s+(?P<percent>\d+)%")
_CHECKOUT = re.compile(r"^(?:Updating|Checking out) files:\s+(?P<percent>\d+)%")
_PRE_PHASES = ("Counting objects:", "Compressing objects:")
_UNIT = {"bytes": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3}
_PERCENT_FULL = 100
_PERCENT_NONE = 0


@dataclass(frozen=True)
class ProgressUpdate:
    """Percent complete and bytes received so far (None when unknown), in *phase*."""

    percent: int | None
    bytes: int | None
    phase: SyncPhase = SyncPhase.DOWNLOADING


def parse_progress(line: str) -> ProgressUpdate | None:
    """A progress update for *line*, or None when the line carries none."""
    text = (line or "").strip()
    if not text:
        return None
    match = _RECEIVING.match(text)
    if match:
        return ProgressUpdate(_percent(match), _size_bytes(match["amount"], match["unit"]))
    if text.startswith(_PRE_PHASES):
        return ProgressUpdate(_PERCENT_NONE, None)
    match = _RESOLVING.match(text)
    if match:
        return ProgressUpdate(_percent(match), None, SyncPhase.RESOLVING)
    match = _CHECKOUT.match(text)
    if match:
        return ProgressUpdate(_percent(match), None, SyncPhase.CHECKOUT)
    return None


def _percent(match: re.Match[str]) -> int:
    return min(int(match["percent"]), _PERCENT_FULL)


def _size_bytes(amount: str | None, unit: str | None) -> int | None:
    if amount is None or unit is None:
        return None
    try:
        return int(float(amount) * _UNIT[unit])
    except (ValueError, OverflowError, KeyError):
        return None
