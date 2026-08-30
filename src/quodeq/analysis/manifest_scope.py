"""Scope filtering for source manifests.

Moved from ``_cli_resolution`` (which re-exports it for CLI callers): the
function operates purely on analysis types, and living here lets in-layer
callers (run start mirrors such as the estimates API) use it without a
layer violation.
"""
from __future__ import annotations

import os

from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.core.observability import NULL_LOG, LogSink


def _filter_manifest_by_scope(
    manifest: SourceManifest | None, scope_path: str, *, log: LogSink = NULL_LOG,
) -> SourceManifest | None:
    """Narrow a manifest to only files under *scope_path*.

    Returns None (with error printed) when no files match.
    """
    if not manifest or not manifest.targets:
        return manifest

    prefix = scope_path.rstrip("/") + "/"
    scoped_targets: list[AnalysisTarget] = []
    total = 0
    all_stats: dict[str, int] = {}

    for t in manifest.targets:
        scoped_files = [f for f in t.source_files if f.startswith(prefix) or f == scope_path]
        if not scoped_files:
            continue
        stats: dict[str, int] = {}
        for f in scoped_files:
            ext = os.path.splitext(f)[1]
            if ext:
                stats[ext] = stats.get(ext, 0) + 1
        scoped_targets.append(AnalysisTarget(
            name=t.name, language=t.language,
            source_files=scoped_files, total_files=len(scoped_files),
            language_stats=stats, category=t.category,
        ))
        total += len(scoped_files)
        for k, v in stats.items():
            all_stats[k] = all_stats.get(k, 0) + v

    if scoped_targets:
        log.info(f"Scope filter: {total} files under '{scope_path}'")
        return SourceManifest(targets=scoped_targets, total_files=total, language_stats=all_stats)

    log.warning(
        f"No source files found under scope '{scope_path}'. "
        "The scoped folder contains no recognized source code files."
    )
    return None
