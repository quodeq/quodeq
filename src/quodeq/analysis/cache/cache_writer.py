"""Factory for the per-file cache-write callback passed to FindingsRouter.

The callback returned by ``build_cache_writer`` is invoked synchronously
by ``FindingsRouter.mark_file_done`` when a worker emits ``status="ok"``.
Captures all fingerprint inputs at construction time so each invocation
only needs ``(file_path, findings)``.

The closure pattern keeps the router itself free of cache-machinery
imports -- the router just calls a function. The cache write is durable
on disk (atomic temp-then-rename via LocalFileBackend) before the
closure returns, so SIGKILL between mark_file_done and the cache write
cannot lose the work.

Key construction MUST match ``dimension_helpers.build_cache_key_for_file``
byte-for-byte; otherwise the parent's ``classify_files_via_cache`` would
MISS what this closure writes. The load-bearing equality test in
``tests/analysis/cache/test_cache_writer.py`` pins that invariant.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from quodeq.analysis.cache.dimension_helpers import (
    _SCHEMA_VERSION,
    _hash_prompts_combined,
)
from quodeq.analysis.cache.entry import CacheEntry, build_provenance, quodeq_version
from quodeq.analysis.cache.key import CacheKey, compute_key
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.fingerprint import _hash_file, _hash_standards, dimension_params_state

_logger = logging.getLogger(__name__)


def build_cache_writer(
    *,
    cache_root: Path,
    src_root: Path,
    standards_dir: Path | None,
    dimension: str,
    model_id: str,
    language: str,
) -> Callable[[str, list[dict]], None]:
    """Return a closure that writes a per-file cache entry on each ok marker.

    The returned closure has signature ``(file_path: str, findings: list[dict]) -> None``.
    It is intended to be passed to ``FindingsRouter(on_file_done=...)`` so the
    router fires it synchronously when ``mark_file_done(status="ok")`` arrives.

    Args:
        cache_root: Directory where ``LocalFileBackend`` stores entries
            (typically ``~/.quodeq/cache/results/``).
        src_root: Project source root -- file content is hashed by reading
            ``src_root / file_path`` at closure-invocation time.
        standards_dir: Compiled standards directory, or None when standards
            are not configured for this run.
        dimension: Dimension identifier (e.g. ``"flexibility"``).
        model_id: Model identifier participating in the cache key --
            ``config.options.subagent_model or config.options.ai_model``
            in the parent's resolution.
        language: Language identifier from the project's manifest.

    Failures (disk full, permission denied, etc.) propagate as exceptions
    out of the closure. The router catches them and logs; the JSONL marker
    write already succeeded, so the run continues.
    """
    cache = LocalFileBackend(root=cache_root)
    # Provenance context, captured once at construction (run-constant). These
    # left the cache key in schema 3 but are recorded on each entry so reuse
    # across a model/prompts/standards boundary is surfaceable, not silent.
    # src_root doubles as the project root whose threshold overrides fold
    # into the standards hash — must match classify's _current_provenance.
    standards_hash = (
        (_hash_standards(standards_dir, dimension, src_root) if standards_dir else "")
        or ""
    )
    prompts_hash = _hash_prompts_combined()
    version = quodeq_version()
    # Computed once at construction: the params_hash keys threshold-override
    # changes into the cache key below; effective_params is wired into
    # provenance in a later task, kept in scope so that wiring is a pure
    # addition here.
    params_hash, effective_params = dimension_params_state(
        standards_dir, dimension, src_root,
    )

    def write(file_path: str, findings: list[dict]) -> None:
        target = src_root / file_path
        try:
            inside = target.resolve().is_relative_to(src_root.resolve())
        except (OSError, ValueError):
            inside = False
        content_hash = (_hash_file(target) or "") if inside else ""
        key_struct = CacheKey(
            schema_version=_SCHEMA_VERSION,
            file_content_hash=content_hash,
            file_path=file_path,
            dimension=dimension,
            language=language,
            params_hash=params_hash,
        )
        key = compute_key(key_struct)
        entry = CacheEntry(
            key=key,
            schema_version=_SCHEMA_VERSION,
            findings=findings,
            files_read=1,
            file_path=file_path,
            dimension=dimension,
            model_id=model_id,
            file_content_hash=content_hash,
            language=language,
            provenance=build_provenance(
                model_id=model_id, prompts_hash=prompts_hash,
                standards_hash=standards_hash, version=version,
            ),
        )
        cache.put(key, entry)

    return write
