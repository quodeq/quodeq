"""Re-export for backward compatibility — moved to quodeq.services.violation_context."""
from quodeq.services.violation_context import (  # noqa: F401
    FindingSpec,
    ViolationContext,
    build_finding_base,
    format_file_line,
)
