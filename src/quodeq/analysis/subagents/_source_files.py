"""Source file listing and filtering for subagent queues."""
from __future__ import annotations

from quodeq.analysis import dispatch_policy
from quodeq.analysis._types import RunConfig
from quodeq.analysis.subagents.priority import PriorityContext, prioritize_files
from quodeq.shared.logging import log_warning


def _resolve_source_files(config: RunConfig) -> tuple[list[str], set[str]] | None:
    """Return (files, extensions) from the target or manifest, preferring the target.

    None when neither the target nor the manifest has source files.
    """
    if config.target is not None and config.target.source_files:
        files = config.target.source_files
        extensions = set(config.target.language_stats.keys()) if config.target.language_stats else set()
        return files, extensions
    if config.manifest is not None and config.manifest.source_files:
        files = config.manifest.source_files
        extensions = set(config.manifest.language_stats.keys()) if config.manifest.language_stats else set()
        return files, extensions
    return None


def _resolve_priority_category(config: RunConfig) -> str | None:
    """Return the target/manifest category used to prioritize files, preferring the target."""
    if config.target and config.target.category:
        return config.target.category
    if config.manifest:
        return config.manifest.category
    return None


def _list_source_files(
    config: RunConfig, dim_id: str, *, ignore_file_filter: bool = False,
) -> tuple[list[str], set[str], list[str]]:
    """List source files for the subagent queue from the target or manifest.

    Returns (files, extensions, excluded) or ([], set(), []) if none found.
    Files are returned in priority order (most important first).

    ``excluded`` holds files the active provider can never dispatch (API
    size cap) — kept out of ``files`` so queues, estimates, and coverage
    denominators all agree with what the worker will actually send.
    """
    resolved = _resolve_source_files(config)
    if resolved is None:
        return [], set(), []
    files, extensions = resolved

    excluded: list[str] = []
    if dispatch_policy.provider_is_api():
        files, excluded = dispatch_policy.split_api_dispatchable(config.src, files)
        if not files:
            return [], extensions, excluded

    # Prioritize files: most important first
    evidence_dir = config.work_dir or config.src
    files = prioritize_files(
        files, config.src, dim_id,
        context=PriorityContext(
            category=_resolve_priority_category(config),
            language=config.language,
            evidence_dir=evidence_dir,
            config=config,
        ),
    )

    # Incremental mode: filter to only changed + dependent files
    if not ignore_file_filter and config.options.incremental_file_filter is not None:
        filter_set = config.options.incremental_file_filter
        files = [f for f in files if f in filter_set]

    return files, extensions, excluded
