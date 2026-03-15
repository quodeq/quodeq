"""Structured marker emission and heartbeat callback for the runner pipeline."""
from __future__ import annotations

import json
import sys
from typing import Callable, TypedDict

from quodeq.shared.logging import log_info

CC_MARKER_KEY = "_cc"  # shared constant for structured job-tracking markers


class _MarkerFields(TypedDict, total=False):
    dimension: str
    dimensions: list[str]


def emit_marker(phase: str, **kwargs: _MarkerFields) -> None:
    """Emit a structured JSON marker (only when stdout is not a TTY)."""
    if sys.stdout.isatty():
        return
    print(json.dumps({CC_MARKER_KEY: phase, **kwargs}), flush=True)


def make_heartbeat(dim_name: str, idx: int, total: int) -> Callable[[int, dict], None]:
    """Return a heartbeat callback that prints progress to stdout."""
    def _cb(elapsed: int, progress: dict) -> None:
        secs = elapsed % 60
        mins = elapsed // 60
        evidence = progress.get("evidence", 0)
        log_info(f"  [{idx}/{total}] {dim_name} | {mins}m{secs:02d}s | {evidence} findings")
    return _cb
