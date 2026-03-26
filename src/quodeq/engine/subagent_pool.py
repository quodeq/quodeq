"""Re-export for backward compatibility -- moved to quodeq.analysis.subagents.pool.

Deprecated: import directly from ``quodeq.analysis.subagents.pool`` instead.
This shim will be removed in a future release.
"""
from quodeq.analysis.subagents.pool import (  # noqa: F401 -- backward-compat re-export
    PoolOptions,
    PoolPaths,
    SubagentPool,
    SubagentResult,
)
