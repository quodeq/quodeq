"""Cache-aware work unit runner — the primitive of the V2 incremental flow.

The contract is intentionally minimal:

    result = analyze_unit(unit, cache, dispatcher)

The runner computes the cache key from ``unit``, consults ``cache``, and
on miss invokes ``dispatcher(unit)`` to produce findings. A successful
dispatch is wrapped in a ``CacheEntry`` (key supplied by the runner, not
the dispatcher) and persisted before returning.

Crash safety: a dispatcher exception propagates and *no* entry is
written. The next invocation with the same inputs misses again and
re-dispatches. There is no half-state to recover from.

This module replaces the implicit fingerprint+JSONL+queue state model.
It is dimension-agnostic and pipeline-agnostic; the existing dispatch
machinery (subagent pool, API runner, ...) plugs in via the
``Dispatcher`` Protocol.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quodeq.analysis.cache.backend import CacheBackend
from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.key import CacheKey, compute_key


@dataclass(frozen=True)
class WorkUnit:
    """One (file, dimension) analysis request and the inputs that key it.

    Hashes are passed in pre-computed so the runner doesn't need to know
    how to read files or hash standards directories. The orchestrator
    builds these once per run and feeds them to the runner per file.
    """

    file_path: str
    file_content_hash: str
    dimension: str
    standards_hash: str
    prompts_hash: str
    evaluator_hash: str
    model_id: str
    language: str
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class DispatchResult:
    """What a dispatcher returns on success.

    The runner wraps this into a ``CacheEntry`` — the dispatcher does not
    know its own cache key and never needs to.
    """

    findings: list[dict]
    files_read: int


class Dispatcher(Protocol):
    """Plugs the existing analysis machinery into the cache runner."""

    def __call__(self, unit: WorkUnit) -> DispatchResult: ...


@dataclass(frozen=True)
class UnitResult:
    """What ``analyze_unit`` returns to the caller."""

    entry: CacheEntry
    cache_hit: bool


def _key_for(unit: WorkUnit, schema_version: int) -> str:
    return compute_key(CacheKey(
        schema_version=schema_version,
        file_content_hash=unit.file_content_hash,
        file_path=unit.file_path,
        dimension=unit.dimension,
        standards_hash=unit.standards_hash,
        prompts_hash=unit.prompts_hash,
        evaluator_hash=unit.evaluator_hash,
        model_id=unit.model_id,
        language=unit.language,
        temperature=unit.temperature,
        max_tokens=unit.max_tokens,
    ))


def analyze_unit(
    unit: WorkUnit,
    *,
    cache: CacheBackend,
    dispatcher: Dispatcher,
    schema_version: int = 1,
) -> UnitResult:
    """Cache-or-dispatch one work unit.

    A miss invokes the dispatcher and writes the result before returning.
    A dispatcher exception propagates without writing — next call retries.
    """
    key = _key_for(unit, schema_version)

    if hit := cache.get(key):
        return UnitResult(entry=hit, cache_hit=True)

    # Crash boundary: any exception below propagates and no entry is
    # written. The cache is only mutated on the success path.
    dispatch_result = dispatcher(unit)

    entry = CacheEntry(
        key=key,
        schema_version=schema_version,
        findings=list(dispatch_result.findings),
        files_read=dispatch_result.files_read,
        file_path=unit.file_path,
        dimension=unit.dimension,
        model_id=unit.model_id,
    )
    cache.put(key, entry)
    return UnitResult(entry=entry, cache_hit=False)
