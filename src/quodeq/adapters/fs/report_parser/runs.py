"""Re-export shim — canonical location is quodeq.data.fs.report_parser.runs."""
from quodeq.data.fs.report_parser.runs import (
    RunInfo,
    RunLookupCache,
    build_repository_info,
    list_runs,
    read_run_data,
    safe_read_dir,
)

__all__ = [
    "RunInfo",
    "RunLookupCache",
    "build_repository_info",
    "list_runs",
    "read_run_data",
    "safe_read_dir",
]
