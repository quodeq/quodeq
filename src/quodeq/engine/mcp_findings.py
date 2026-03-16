"""Re-export for backward compatibility — moved to quodeq.analysis.mcp.findings_server."""
from quodeq.analysis.mcp.findings_server import (  # noqa: F401
    FindingsRouter,
    main,
)
from quodeq.engine._ref_utils import (  # noqa: F401
    ref_label,
    load_compiled_refs,
)
