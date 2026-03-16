"""Re-export for backward compatibility — moved to quodeq.analysis.stream.parser."""
from quodeq.analysis.stream.parser import (  # noqa: F401
    FINDING_TYPE_VIOLATION,
    FINDING_TYPE_COMPLIANCE,
    extract_evidence_from_stream,
    _extract_jsonl_from_text,
    _extract_read_paths,
    _collect_file_reads,
    _process_texts,
)
