"""Date parsing helpers for run directories."""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from quodeq.shared.logging import log_debug
from quodeq.shared.utils import TEXT_ENCODING


def normalize_date(raw: str) -> tuple[str, str] | None:
    """Parse a date/datetime string and return (sortable_iso, human_label).

    Accepts ISO datetime (2026-03-01T14:30:25), ISO date (2026-03-01),
    or compact date (20260301).  The first element is the full string
    (including time when available) so that same-day runs sort correctly.
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            sortable = parsed.isoformat(timespec='seconds') if "T" in fmt else parsed.date().isoformat()
            label = f"{parsed.year}-{parsed.month:02d}-{parsed.day:02d}"
            return sortable, label
        except ValueError:
            continue
    return None


def find_date_in_dir(
    directory: Path, suffix: str, safe_read_dir: Callable[[Path], list[os.DirEntry[str]]],
) -> tuple[str | None, str] | None:
    """Scan JSON files in *directory* matching *suffix* for a parsable date field."""
    for entry in safe_read_dir(directory):
        if not entry.is_file() or not entry.name.endswith(suffix):
            continue
        try:
            data = json.loads(Path(entry.path).read_text(encoding=TEXT_ENCODING))
            raw = data.get("date")
            if raw:
                result = normalize_date(str(raw))
                if result:
                    return result
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            log_debug(f"Failed to read date from {entry.name}: {exc}")
    return None
