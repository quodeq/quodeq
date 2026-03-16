"""Re-export for backward compatibility — moved to quodeq.services.violations_parsing."""
from quodeq.services.violations_parsing import (  # noqa: F401
    parse_violations_from_jsonl,
    parse_violations_from_evidence,
    parse_violations_from_stream,
)
