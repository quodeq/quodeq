"""Re-export for backward compatibility — moved to quodeq.analysis.mcp.findings_server.

Reference utilities (ref_label, load_compiled_refs) should be imported
directly from ``quodeq.engine._ref_utils``.
"""
from quodeq.analysis.mcp.findings_server import (  # noqa: F401
    FindingsRouter,
    main,
)
