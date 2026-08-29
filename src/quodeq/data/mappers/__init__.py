"""Raw-dict -> core.types dataclass deserialization (adapter layer).

Translating external JSON shapes (snake/camelCase wire payloads, report
files) into core entities is adapter work, so it lives here in ``data``
rather than beside the entities themselves. All mapper functions are split
by entity type into private modules; ``from quodeq.data.mappers import X``
is the public surface via these re-exports.
"""

from __future__ import annotations

from ._mapper_findings import (
    _parse_finding_list,
    parse_finding,
    parse_req_ref,
    parse_severity_tally,
    parse_totals,
)
from ._mapper_reports import (
    parse_evidence_file_meta,
    parse_parsed_report,
    parse_principle_grade,
)
from ._mapper_dimensions import (
    parse_dimension_result,
    parse_dimension_summary,
    parse_grade_breakdown,
)
from ._mapper_projects import (
    parse_job_snapshot,
    parse_project_entry,
    parse_project_metadata,
)
from ._mapper_plugins import (
    parse_plugin_dimension,
    parse_plugin_info,
)
from ._mapper_violations import (
    _parse_progress_info,
    _parse_violation_file_entry,
    parse_trend_point,
    parse_violation_response,
    parse_violation_summary,
)


__all__ = [
    # findings
    "parse_finding",
    "parse_req_ref",
    "parse_severity_tally",
    "parse_totals",
    # dimensions
    "parse_dimension_result",
    "parse_dimension_summary",
    "parse_evidence_file_meta",
    "parse_grade_breakdown",
    "parse_parsed_report",
    "parse_principle_grade",
    # projects & jobs
    "parse_job_snapshot",
    "parse_project_entry",
    "parse_project_metadata",
    # plugins
    "parse_plugin_dimension",
    "parse_plugin_info",
    # violations & trends
    "parse_trend_point",
    "parse_violation_response",
    "parse_violation_summary",
]
