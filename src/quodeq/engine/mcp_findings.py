"""Re-export for backward compatibility — moved to quodeq.analysis.mcp.findings_server."""
from quodeq.analysis.mcp.findings_server import (  # noqa: F401
    FindingsRouter,
    main,
    _FINDING_SCHEMA_VERSION,
    _STOP_WORDS,
    _text_overlap,
    _select_best_refs,
)
# Re-export names that were imported into the original module's namespace
from quodeq.engine._ref_utils import (  # noqa: F401
    ref_label as _ref_label,
    load_compiled_refs as _load_compiled_refs,
)
