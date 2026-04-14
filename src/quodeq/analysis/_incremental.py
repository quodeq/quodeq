"""Incremental dimension analysis — re-export hub for backward compatibility.

This module re-exports symbols from their canonical locations so that
existing callers (``_pipeline.py``, tests, etc.) can import from a single
place.  Canonical modules: ``_incremental_context``, ``_incremental_evidence``,
``_incremental_phases``, ``_incremental_orchestrator``, ``_loops``,
``fingerprint``, and ``subagents._source_files``.
"""
from __future__ import annotations

from quodeq.analysis._incremental_context import (  # noqa: F401
    IncrementalCoverage,
    load_analysis_context,
)
from quodeq.analysis._incremental_evidence import (  # noqa: F401
    _extract_files_from_jsonl,
    parse_evidence_from_jsonl as _parse_evidence_from_jsonl,
    save_dimension_fingerprint,
)
from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint  # noqa: F401
from quodeq.analysis.subagents._source_files import _list_source_files  # noqa: F401
from quodeq.analysis._incremental_phases import (  # noqa: F401
    _finalize_incremental,
    _list_all_source_files,
    _maybe_carry_forward,
    _run_phase1_analysis,
)
from quodeq.analysis._incremental_orchestrator import (  # noqa: F401
    run_dimension_incremental,
)

# Re-export loop orchestrators from _loops.py for backward compatibility
from quodeq.analysis._loops import (  # noqa: F401
    check_zero_findings,
    run_incremental_loop,
    run_per_dimension_loop,
)
