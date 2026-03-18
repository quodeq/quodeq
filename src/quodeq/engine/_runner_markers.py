"""Structured marker emission and heartbeat callback for the runner pipeline."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from quodeq.shared.logging import log_info

CC_MARKER_KEY = "_cc"  # shared constant for structured job-tracking markers
_SECONDS_PER_MINUTE = 60


def emit_marker(phase: str, **kwargs: Any) -> None:
    """Emit a structured JSON marker (only when stdout is not a TTY)."""
    if sys.stdout.isatty():
        return
    print(json.dumps({CC_MARKER_KEY: phase, **kwargs}), flush=True)


def cleanup_stream(stream_file: Path) -> None:
    """Remove stream and stderr files after successful evidence extraction."""
    stream_file.unlink(missing_ok=True)
    err_file = Path(str(stream_file) + ".err")
    err_file.unlink(missing_ok=True)


def make_heartbeat(dim_name: str, idx: int, total: int) -> Callable[[int, dict], None]:
    """Return a heartbeat callback that prints progress to stdout."""
    def _cb(elapsed: int, progress: dict) -> None:
        secs = elapsed % _SECONDS_PER_MINUTE
        mins = elapsed // _SECONDS_PER_MINUTE
        evidence = progress.get("evidence", 0)
        log_info(f"  [{idx}/{total}] {dim_name} | {mins}m{secs:02d}s | {evidence} findings")
    return _cb
