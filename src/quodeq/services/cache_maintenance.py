"""Background result-cache maintenance for the dashboard process.

The CLI pipeline runs ``ensure_cache_ready`` inline at run start. The
dashboard serves estimates on the request path, where a minutes-long
migration would time out a request, so it runs the same maintenance once on
a daemon thread at startup. Estimates requested during that window may
undercount cached files; that is transient and self-heals on the next
request.
"""
from __future__ import annotations

import threading
from pathlib import Path

from quodeq.config.paths import default_paths
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.cache_store.local import default_cache_root
from quodeq.data.cache_store.migrate import ensure_cache_ready
from quodeq.shared.fault_isolation import run_isolated


def _default_standards_dir() -> Path | None:
    try:
        std = default_paths().standards_dir
    except OSError:
        return None
    return std if std is not None and std.exists() else None


def start_cache_maintenance(
    root: Path | None = None, *, standards_dir: Path | None = None,
    log: LogSink = NULL_LOG,
) -> threading.Thread:
    """Start ``ensure_cache_ready`` on a daemon thread and return it."""
    target_root = root if root is not None else default_cache_root()
    std = standards_dir if standards_dir is not None else _default_standards_dir()

    def _run() -> None:
        run_isolated(lambda: ensure_cache_ready(target_root, standards_dir=std), label="cache maintenance", log=log)

    thread = threading.Thread(target=_run, name="cache-maintenance", daemon=True)
    thread.start()
    return thread
