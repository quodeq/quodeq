"""Source file listing and filtering for subagent queues."""
from __future__ import annotations

from quodeq.analysis._types import RunConfig
from quodeq.analysis.subagents.priority import PriorityContext, prioritize_files
from quodeq.shared.logging import log_warning


def _list_source_files(
    config: RunConfig, dim_id: str, *, ignore_file_filter: bool = False,
) -> tuple[list[str], set[str]]:
    """List source files for the subagent queue from the target or manifest.

    Returns (files, extensions) or ([], set()) if none found.
    Files are returned in priority order (most important first).
    """
    # Prefer target-scoped files when available
    if config.target is not None and config.target.source_files:
        files = config.target.source_files
        extensions = set(config.target.language_stats.keys()) if config.target.language_stats else set()
    elif config.manifest is not None and config.manifest.source_files:
        files = config.manifest.source_files
        extensions = set(config.manifest.language_stats.keys()) if config.manifest.language_stats else set()
    else:
        return [], set()

    # Prioritize files: most important first
    category = None
    if config.target and config.target.category:
        category = config.target.category
    elif config.manifest:
        category = config.manifest.category

    evidence_dir = config.work_dir or config.src
    files = prioritize_files(
        files, config.src, dim_id,
        context=PriorityContext(
            category=category,
            language=config.language,
            evidence_dir=evidence_dir,
            config=config,
        ),
    )

    # Incremental mode: filter to only changed + dependent files
    if not ignore_file_filter and config.options.incremental_file_filter is not None:
        filter_set = config.options.incremental_file_filter
        files = [f for f in files if f in filter_set]

    return files, extensions
