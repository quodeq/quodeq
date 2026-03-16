"""Re-export for backward compatibility — moved to quodeq.analysis.stream.counters."""
from quodeq.analysis.stream.counters import (  # noqa: F401
    extract_files_from_blocks,
    parse_stream_event,
    extract_files_from_event,
    count_files_in_stream,
    count_jsonl_lines,
)
