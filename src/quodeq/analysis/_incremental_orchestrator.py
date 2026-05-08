"""Incremental analysis — top-level orchestrator for a single dimension.

Post-V2 (B6): the V2 content-addressed cache owns change detection.
This module is now a thin wrapper that delegates to the standard
dimension processor; both incremental and clean-scan paths converge
on the same code path inside ``_process_single_dimension``, which in
turn routes through ``process_dimension_with_cache``.

The incremental vs clean-scan distinction is preserved via
``config.options.incremental`` — when False, the cache layer bypasses
reads (clean-scan refresh) but still writes fresh entries.
"""
from __future__ import annotations

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.core.evidence.model import Evidence


def run_dimension_incremental(
    config: RunConfig, dimension: str, idx: int, ctx: _AnalysisContext,
) -> Evidence | None:
    """V2-native incremental: classify via cache, dispatch misses, assemble.

    The orchestration that used to live here (V1's classify_files +
    carry-forward + phase1 + backfill + finalize) is now entirely owned
    by the cache layer. The ``(incremental)`` log line is emitted by
    the caller in ``_loops.run_incremental_loop``.
    """
    # Deferred import: avoids a circular dependency between
    # _incremental_orchestrator and _dimension_ops.
    from quodeq.analysis._dimension_ops import _process_single_dimension
    return _process_single_dimension(config, dimension, idx, ctx, emit_log=False)
