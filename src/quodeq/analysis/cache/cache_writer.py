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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from quodeq.analysis.run_types import RunConfig
from quodeq.analysis.cache._key_provenance import _content_hash_for
from quodeq.analysis.cache.dimension_helpers import (
    _SCHEMA_VERSION,
    _hash_prompts_combined,
)
from quodeq.analysis.cache.entry import CacheEntry, build_provenance, quodeq_version
from quodeq.analysis.cache.key import CacheKey, compute_key
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.fingerprint import hash_standards, dimension_params_state

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriterProvenance:
    """Cache-writer provenance context, resolved once per closure.

    These left the cache key in schema 3 but are recorded on each entry so
    reuse across a model/prompts/standards boundary is surfaceable, not
    silent. ``params_hash`` keys threshold-override changes into the cache
    key; ``effective_params`` is recorded on each entry's provenance so the
    resolved thresholds findings were judged under are surfaceable.
    """

    standards_hash: str
    prompts_hash: str
    version: str
    params_hash: str
    effective_params: dict


@dataclass(frozen=True)
class CacheWriteTarget:
    """Where one closure invocation's entry lands, and the identity fields
    stamped on it: the backend, the project root file content is hashed
    against, and the dimension/language/model on every entry it writes."""

    cache: LocalFileBackend
    src_root: Path
    dimension: str
    language: str
    model_id: str
    # file_path -> content hash already computed at classify time (""
    # when a miss couldn't be hashed). A file absent from this mapping
    # falls back to hashing it directly. Empty by default so callers that
    # never pass one (e.g. the MCP server) keep hashing as before.
    content_hashes: Mapping[str, str] = field(default_factory=dict)
    # file_path -> the file's ``stat_key`` when classify hashed it. The
    # hash above is reused only while it still matches; a file missing
    # here is hashed at write time. See ``_key_provenance._content_hash_for``.
    content_stamps: Mapping[str, tuple[int, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class CacheWriterSpec:
    """Everything ``build_cache_writer`` needs to construct one closure."""

    cache_root: Path
    src_root: Path
    standards_dir: Path | None
    prompts_dir: Path | None
    dimension: str
    model_id: str
    language: str
    # file_path -> content hash already computed at classify time, and the
    # stat stamp it was read under. See CacheWriteTarget's two fields;
    # threaded straight through to them.
    content_hashes: Mapping[str, str] = field(default_factory=dict)
    content_stamps: Mapping[str, tuple[int, int]] = field(default_factory=dict)

    @classmethod
    def from_run_config(
        cls, run_config: RunConfig, dim_id: str, cache_root: Path,
        content_hashes: Mapping[str, str] | None = None,
        content_stamps: Mapping[str, tuple[int, int]] | None = None,
    ) -> "CacheWriterSpec":
        """Resolve a spec from the ``_api_runner`` composition root's RunConfig.

        *content_hashes* / *content_stamps* are the dimension's
        ClassifyResult.miss_hashes and .miss_stamps when the caller has one in
        scope (see ``_api_runner._build_cache_writer``); left ``None``,
        entries hash their file directly, as before.
        """
        model_id = (
            run_config.options.subagent_model
            or run_config.options.ai_model
            or "unknown"
        )
        return cls(
            cache_root=cache_root, src_root=run_config.src,
            standards_dir=run_config.standards_dir, prompts_dir=run_config.prompts_dir,
            dimension=dim_id, model_id=model_id, language=run_config.language or "",
            content_hashes=content_hashes or {},
            content_stamps=content_stamps or {},
        )


def _resolve_writer_provenance(
    dimension: str, src_root: Path, standards_dir: Path | None, prompts_dir: Path | None,
) -> WriterProvenance:
    """Resolve cache-writer provenance context, computed once per closure.

    ``src_root`` doubles as the project root whose threshold overrides fold
    into the standards hash — must match classify's ``_current_provenance``.
    """
    standards_hash = (
        (hash_standards(standards_dir, dimension, src_root) if standards_dir else "")
        or ""
    )
    prompts_hash = _hash_prompts_combined(prompts_dir)
    version = quodeq_version()
    params_hash, effective_params = dimension_params_state(
        standards_dir, dimension, src_root,
    )
    return WriterProvenance(
        standards_hash=standards_hash, prompts_hash=prompts_hash, version=version,
        params_hash=params_hash, effective_params=effective_params,
    )


def _entry_content_hash(target: CacheWriteTarget, file_path: str) -> str:
    """The content hash this file's entry is keyed on.

    A path that escapes ``src_root`` is never read: it keeps the empty hash
    it has always had (such an entry is not adoptable, which is the point).
    Everything else goes through the shared
    ``_key_provenance._content_hash_for``, so this path and the
    dispatch-persist path key entries on the same rules.
    """
    resolved = target.src_root / file_path
    try:
        inside = resolved.resolve().is_relative_to(target.src_root.resolve())
    except (OSError, ValueError):
        inside = False
    if not inside:
        return ""
    return _content_hash_for(
        resolved,
        target.content_hashes.get(file_path),
        target.content_stamps.get(file_path),
    )


def _write_cache_entry(
    target: CacheWriteTarget, file_path: str, findings: list[dict],
    provenance: WriterProvenance,
) -> None:
    """Build the CacheEntry for one file's findings and persist it.

    Key construction MUST match ``dimension_helpers.build_cache_key_for_file``
    byte-for-byte; otherwise the parent's ``classify_files_via_cache`` would
    MISS what this writes. Pinned by ``tests/analysis/cache/test_cache_writer.py``.
    """
    content_hash = _entry_content_hash(target, file_path)
    key_struct = CacheKey(
        schema_version=_SCHEMA_VERSION,
        file_content_hash=content_hash,
        file_path=file_path,
        dimension=target.dimension,
        params_hash=provenance.params_hash,
    )
    key = compute_key(key_struct)
    entry = CacheEntry(
        key=key,
        schema_version=_SCHEMA_VERSION,
        findings=findings,
        files_read=1,
        file_path=file_path,
        dimension=target.dimension,
        model_id=target.model_id,
        file_content_hash=content_hash,
        language=target.language,
        params_hash=provenance.params_hash,
        provenance=build_provenance(
            model_id=target.model_id, prompts_hash=provenance.prompts_hash,
            standards_hash=provenance.standards_hash, version=provenance.version,
            effective_params=provenance.effective_params,
        ),
        # Born unconsolidated: no completed run has these findings in its
        # report yet. mark_run_consolidated flips it when this run ends done.
        consolidated=False,
    )
    target.cache.put(key, entry)


def build_cache_writer(spec: CacheWriterSpec) -> Callable[[str, list[dict]], None]:
    """Return a closure that writes a per-file cache entry on each ok marker.

    The returned closure has signature ``(file_path: str, findings: list[dict]) -> None``.
    It is intended to be passed to ``FindingsRouter(on_file_done=...)`` so the
    router fires it synchronously when ``mark_file_done(status="ok")`` arrives.

    ``spec.prompts_dir`` MUST match what classify-time ``_current_provenance``
    hashes, or reused entries report phantom prompts drift.

    Failures (disk full, permission denied, etc.) propagate as exceptions
    out of the closure. The router catches them and logs; the JSONL marker
    write already succeeded, so the run continues.
    """
    cache = LocalFileBackend(root=spec.cache_root)
    provenance = _resolve_writer_provenance(
        spec.dimension, spec.src_root, spec.standards_dir, spec.prompts_dir,
    )
    target = CacheWriteTarget(
        cache=cache, src_root=spec.src_root, dimension=spec.dimension,
        language=spec.language, model_id=spec.model_id,
        content_hashes=spec.content_hashes, content_stamps=spec.content_stamps,
    )

    def write(file_path: str, findings: list[dict]) -> None:
        _write_cache_entry(target, file_path, findings, provenance)

    return write
