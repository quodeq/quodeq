"""Single source of truth for which files an API provider can dispatch.

API providers (Ollama, omlx, ...) inline file contents into the prompt, so
oversized files cannot be dispatched and are capped by
``QUODEQ_MAX_API_FILE_SIZE``. CLI providers (claude, gemini, codex) read
files through their own tools and have no such cap.

The queue builder / estimates (``_list_source_files``) and the dispatch-time
worker (``_gather_api_source_files``) MUST share this predicate. When they
diverged, files entered the queue, were taken, then silently dropped at
dispatch: no ``file_done`` marker, no cache entry, re-queued as misses on
every incremental run — and dim coverage never converged to 100%.
"""
from __future__ import annotations

import os
from pathlib import Path

from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.shared.utils import get_ai_cmd

_DEFAULT_MAX_API_FILE_SIZE = 15000


def api_file_size_cap() -> int:
    """Max file size (bytes, exclusive) an API provider will dispatch."""
    raw = os.environ.get("QUODEQ_MAX_API_FILE_SIZE", "")
    try:
        return int(raw) if raw else _DEFAULT_MAX_API_FILE_SIZE
    except ValueError:
        return _DEFAULT_MAX_API_FILE_SIZE


def provider_is_api(ai_cmd: str | None = None) -> bool:
    """True when the active (or given) provider dispatches via direct API."""
    cmd = ai_cmd or get_ai_cmd()
    return get_provider_configs().get(cmd, {}).get("type", "cli") == "api"


def split_api_dispatchable(
    root: Path, rel_files: list[str],
) -> tuple[list[str], list[str]]:
    """Split *rel_files* into (dispatchable, excluded), preserving order.

    A file is excluded when it is missing/unreadable or its size reaches
    ``api_file_size_cap()`` — exactly the set an API worker cannot send.
    """
    cap = api_file_size_cap()
    dispatchable: list[str] = []
    excluded: list[str] = []
    for f in rel_files:
        try:
            size = (root / f).stat().st_size
        except OSError:
            excluded.append(f)
            continue
        (dispatchable if size < cap else excluded).append(f)
    return dispatchable, excluded
