"""Re-export shim — canonical location is quodeq.data.fs.report_parser.json_parser."""
from quodeq.data.fs.report_parser.json_parser import (
    empty_severity_buckets,
    parse_eval_from_json,
    parse_evidence_file,
    parse_report_json,
)

__all__ = [
    "empty_severity_buckets",
    "parse_eval_from_json",
    "parse_evidence_file",
    "parse_report_json",
]
