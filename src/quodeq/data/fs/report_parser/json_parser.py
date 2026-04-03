"""Parsers for JSON-format evaluation reports and evidence files.

This module re-exports from focused sub-modules for backward compatibility.
"""

from quodeq.data.fs.report_parser._eval_parsing import parse_eval_from_json
from quodeq.data.fs.report_parser._report_parsing import (
    build_finding,
    empty_severity_buckets,
    parse_evidence_file,
    parse_report_json,
)

__all__ = [
    "build_finding",
    "empty_severity_buckets",
    "parse_eval_from_json",
    "parse_evidence_file",
    "parse_report_json",
]
