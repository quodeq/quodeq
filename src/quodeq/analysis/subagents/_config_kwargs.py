"""Shared AnalysisConfig kwargs for the subagent launch builders."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from quodeq.analysis.run_types import RunConfig


def shared_analysis_config_kwargs(config: "RunConfig") -> dict[str, Any]:
    """Return the AnalysisConfig fields common to every subagent launch mode.

    Both the consolidated-mode builder (``_consolidated._build_consolidated_config``)
    and the per-dimension pool builder (``_pool_launcher._build_pool_config``)
    spread this into their ``AnalysisConfig(...)`` call. ``compiled_dir`` and
    ``ai_model`` are deliberately excluded: each caller computes those
    differently and passes its own value in.

    ``drop_counter`` and ``mcp_registry`` are filled here too, so both modes
    reach the run's owners even when a caller (the consolidated builder)
    deliberately leaves ``run_config`` unset.
    """
    return {
        "analysis_budget": config.options.analysis_budget,
        "max_turns": config.options.max_turns,
        "max_duration": config.options.max_duration,
        "ai_cmd": config.ai_cmd,
        "ai_cmd_path": config.options.ai_cmd_path,
        "cache_root": config.options.cache_root,
        "drop_counter": config.drop_counter,
        "mcp_registry": config.mcp_registry,
    }
