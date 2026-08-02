"""Stream and JSONL file counting helpers for AI analysis output.

The pure parsers moved to ``core/stream/events.py`` and the file-reading
counters to ``data/fs/stream_files.py``; this module stays as the
analysis-side name for both.
"""
from __future__ import annotations

from quodeq.core.stream.events import (  # noqa: F401 — re-exported API
    extract_files_from_blocks,
    extract_files_from_event,
    parse_stream_event,
)
from quodeq.data.fs.stream_files import (  # noqa: F401 — re-exported API
    count_files_in_stream,
    count_jsonl_lines,
)
