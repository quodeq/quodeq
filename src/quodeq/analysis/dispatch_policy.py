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

``DispatchPolicy`` bundles the three inputs that decide dispatchability
(provider configs, active AI command, file-size cap) into one frozen value,
so a ``RunConfig``, the queue builder, and the dispatch-time worker can all
resolve the SAME values for one run instead of each independently
re-reading env/provider-cache state. ``default_dispatch_policy()`` is the
factory that resolves those live values; the three module-level functions
below are thin back-compat wrappers over a freshly-built policy, kept for
existing callers that don't carry a ``RunConfig``/``DispatchPolicy`` around.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.analysis._provider_cache import get_provider_configs
from quodeq.shared.utils import get_ai_cmd

_DEFAULT_MAX_API_FILE_SIZE = 15000

StatFn = Callable[[Path], int]


def _real_stat_size(path: Path) -> int:
    """``path.stat().st_size``; raises OSError for a missing/unreadable file."""
    return path.stat().st_size


def api_file_size_cap(env: dict[str, str] | None = None) -> int:
    """Max file size (bytes, exclusive) an API provider will dispatch."""
    raw = (env if env is not None else os.environ).get("QUODEQ_MAX_API_FILE_SIZE", "")
    try:
        return int(raw) if raw else _DEFAULT_MAX_API_FILE_SIZE
    except ValueError:
        return _DEFAULT_MAX_API_FILE_SIZE


@dataclass(frozen=True)
class DispatchPolicy:
    """Frozen snapshot of everything that decides API dispatchability.

    *stat_size* is the file-size lookup seam: tests inject a fake mapping
    instead of writing real files to disk.
    """
    provider_configs: dict[str, dict]
    ai_cmd: str
    file_size_cap: int
    stat_size: StatFn = _real_stat_size

    def provider_is_api(self) -> bool:
        """True when the active provider dispatches via direct API."""
        return self.provider_configs.get(self.ai_cmd, {}).get("type", "cli") == "api"

    def split_api_dispatchable(
        self, root: Path, rel_files: list[str],
    ) -> tuple[list[str], list[str]]:
        """Split *rel_files* into (dispatchable, excluded), preserving order.

        A file is excluded when it is missing/unreadable or its size
        reaches ``file_size_cap`` — exactly the set an API worker cannot
        send.
        """
        dispatchable: list[str] = []
        excluded: list[str] = []
        for f in rel_files:
            try:
                size = self.stat_size(root / f)
            except OSError:
                excluded.append(f)
                continue
            (dispatchable if size < self.file_size_cap else excluded).append(f)
        return dispatchable, excluded


def default_dispatch_policy(
    *,
    env: dict[str, str] | None = None,
    provider_configs: dict[str, dict] | None = None,
    ai_cmd: str | None = None,
    stat_size: StatFn = _real_stat_size,
) -> DispatchPolicy:
    """Build a :class:`DispatchPolicy` from the live environment / provider cache.

    Each keyword overrides the corresponding live lookup — tests build a
    fully literal policy by supplying all three plus *stat_size* (no env, no
    provider cache, no real files).
    """
    return DispatchPolicy(
        provider_configs=provider_configs if provider_configs is not None else get_provider_configs(),
        ai_cmd=ai_cmd if ai_cmd is not None else get_ai_cmd(env),
        file_size_cap=api_file_size_cap(env),
        stat_size=stat_size,
    )


def provider_is_api(ai_cmd: str | None = None) -> bool:
    """True when the active (or given) provider dispatches via direct API.

    Thin back-compat wrapper over a freshly-built :func:`default_dispatch_policy`.
    """
    cmd = ai_cmd or get_ai_cmd()
    return default_dispatch_policy(ai_cmd=cmd).provider_is_api()


def split_api_dispatchable(
    root: Path, rel_files: list[str],
) -> tuple[list[str], list[str]]:
    """Split *rel_files* into (dispatchable, excluded), preserving order.

    Thin back-compat wrapper over a freshly-built :func:`default_dispatch_policy`.
    """
    return default_dispatch_policy().split_api_dispatchable(root, rel_files)
