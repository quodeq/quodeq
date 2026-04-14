"""Incremental analysis context — dimension loading and resolution."""
from __future__ import annotations

import json as _json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from quodeq.analysis._types import RunConfig, _AnalysisContext
from quodeq.analysis.prompts.builder import load_template
from quodeq.config.paths import default_paths
from quodeq.shared.logging import log_warning


@dataclass
class IncrementalCoverage:
    """Groups coverage-related data for incremental finalization."""
    files: list[str]
    all_analyzed: set[str]
    files_read: int


def _load_custom_dimensions(evaluators_dir: Path, dims_data: list[str]) -> list[str]:
    """Load evaluator IDs from JSON files in *evaluators_dir* not already in *dims_data*."""
    result = list(dims_data)
    seen = set(result)
    for _p in evaluators_dir.glob("*.json"):
        try:
            _eid = _json.loads(_p.read_text()).get("id")
            if _eid and _eid not in seen:
                result.append(_eid)
                seen.add(_eid)
        except (OSError, ValueError, KeyError):
            pass
    return result


def load_analysis_context(config: "RunConfig") -> tuple[list[str], "_AnalysisContext"]:
    """Load dimensions data and resolve which dimensions to analyze."""
    dims_data = config.dimensions_data
    if dims_data is None:
        raise ValueError("RunConfig.dimensions_data is required")

    all_dims_raw = [d.get("id") for d in dims_data.get("applies", []) if d.get("id")]

    # Include custom evaluators from evaluators directory (only when dimensions are explicitly requested)
    if config.options.dimensions:
        _evaluators_dir = getattr(config, 'evaluators_dir', None)
        if _evaluators_dir is None:
            _evaluators_dir = default_paths().evaluators_dir
    else:
        _evaluators_dir = None
    if _evaluators_dir and _evaluators_dir.is_dir():
        all_dims_raw = _load_custom_dimensions(_evaluators_dir, all_dims_raw)

    if config.options.dimensions:
        all_dims_set = set(all_dims_raw)
        unknown = [d for d in config.options.dimensions if d not in all_dims_set]
        if unknown:
            log_warning(f"Unknown dimensions ignored: {', '.join(unknown)}. "
                        f"Available: {', '.join(all_dims_raw)}")
        dimensions = [d for d in all_dims_raw if d in config.options.dimensions]
        if not dimensions:
            raise ValueError(
                f"No valid dimensions selected. "
                f"Requested: {', '.join(config.options.dimensions)}. "
                f"Available: {', '.join(all_dims_raw)}"
            )
    else:
        dimensions = all_dims_raw

    ctx = _AnalysisContext(
        dimensions_data=dims_data,
        date_str=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        template=load_template(config.options.template_path),
        subagent_template=load_template(template_name="cli_subagent_prompt.md"),
        total=len(dimensions),
    )
    return dimensions, ctx
