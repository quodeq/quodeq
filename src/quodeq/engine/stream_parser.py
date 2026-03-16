"""Re-export for backward compatibility — moved to quodeq.analysis.stream.parser."""
from quodeq.analysis.stream.parser import *  # noqa: F401,F403
from quodeq.analysis.stream.parser import (  # noqa: F401
    _extract_jsonl_from_text,
    _extract_read_paths,
    _collect_file_reads,
    _process_texts,
)
