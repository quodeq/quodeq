"""API runner for direct LLM evaluation.

Calls LLM APIs directly via the raw OpenAI client and writes findings as
JSONL evidence -- the same format the CLI runner produces via MCP.

``_Finding`` (in ``_api_schema``) is a lenient short-key variant of the
canonical ``Judgment`` (``quodeq.core.events.models``). Local models drop
required fields and balk at long field names under load -- this type's short
keys (``req``/``t``/``w``) and Field descriptions are tuned for that
constraint. The downstream wire-dict → Judgment lift happens via
``quodeq.core.finding_mappings.wire_dict_to_judgment`` after
``FindingEnricher`` maps ``req`` to ``practice_id``.

Requires the ``quodeq[api]`` extra: ``pip install 'quodeq[api]'``
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

# Kept so `patch("...._api_runner.openai.OpenAI")` still resolves -- the
# real call site (`_call_api`) lives in `_api_call`, but patching an
# attribute on this shared module object affects it there too.
import openai

from quodeq.analysis._api_call import (
    ApiRunnerConfig,
    _CLOUD_TIMEOUT,
    _DEFAULT_LOCAL_MAX_TOKENS,
    _LOCAL_TIMEOUT,
    _OLLAMA_DEFAULT_API_KEY,
    _OLLAMA_DEFAULT_BASE,
    _OPENAI_API_HOST,
    _build_create_kwargs,
    _call_api,
    _classify_fatal_api_error,
    _log_call_outcome,
    _resolve_max_tokens,
    _resolve_timeout,
    _warn_ollama_ctx_noop,
)
from quodeq.analysis._api_enrichment import (
    _derive_run_paths,
    _infer_end_line,
    _resolve_file_paths,
)
from quodeq.analysis._api_schema import (
    _SYSTEM_PROMPT,
    _Finding,
    _FindingType,
    _Severity,
    _extract_finding_dicts,
    _looks_like_finding,
    _parse_findings,
)
from quodeq.analysis.errors import FatalProviderError
from quodeq.analysis.mcp.router import CompiledContext, FindingsRouter

if TYPE_CHECKING:
    from quodeq.analysis._types import RunConfig
    from quodeq.data.events.writer import EventLogWriter
from quodeq.context.precedent import load_precedent_corpus, load_precedent_fingerprints
from quodeq.context.project_shape import detect_shape
from quodeq.context.trust_model import resolve_trust_model
from quodeq.data.fs.standards_loader import load_compiled_refs, load_compiled_requirements
from quodeq.data.sqlite.findings_queries import (
    dismissed_source_stamp,
    read_dismissed_snippets_strict,
)

_log = logging.getLogger(__name__)


def _build_router_context(
    compiled_dir: Path | None,
    dimension: str | None,
    work_dir: Path | None,
    project_dir: Path | None,
    run_dir: Path | None,
) -> CompiledContext | None:
    """Build the CompiledContext that FindingsRouter needs for enrichment.

    Returns ``None`` when *compiled_dir* is unset, signalling that the
    caller should write findings without enrichment (legacy behaviour).

    *run_dir* locates the run directory holding the semantic precedent
    corpus's circuit-breaker marker (see ``load_precedent_corpus``).
    """
    if not compiled_dir:
        return None
    try:
        compiled_refs = load_compiled_refs(compiled_dir, dimension) or {}
        compiled_reqs = load_compiled_requirements(compiled_dir, dimension) or {}
        project_shape = detect_shape(work_dir) if work_dir is not None else None
        trust_model = resolve_trust_model(work_dir) if work_dir is not None else None
        # The strict reader raises on a failed open, so the per-run memo skips
        # the run instead of remembering it as having no dismissals.
        precedents = (
            load_precedent_fingerprints(
                project_dir, read_dismissed=read_dismissed_snippets_strict,
                source_stamp=dismissed_source_stamp,
            )
            if project_dir else set()
        )
        corpus = (
            load_precedent_corpus(project_dir, run_dir)
            if project_dir and run_dir else None
        )
        return CompiledContext(
            compiled_refs=compiled_refs,
            compiled_reqs=compiled_reqs,
            dimension=dimension,
            work_dir=work_dir,
            project_shape=project_shape,
            trust_model=trust_model,
            precedent_fingerprints=precedents,
            precedent_corpus=corpus,
        )
    except Exception as exc:  # noqa: BLE001 - degrade gracefully to raw findings on enrichment setup failure
        _log.warning("Could not build enrichment context: %s -- writing raw", exc)
        return None


def _build_event_log(run_dir: Path):
    """EventLogWriter on the run's ``events.jsonl``.

    Lazy import: ``quodeq.data.events`` stays off the import path for
    callers that never reach the write phase.
    """
    from quodeq.data.events.writer import EventLogWriter  # noqa: PLC0415
    return EventLogWriter(run_dir / "events.jsonl")


def _build_cache_writer(
    run_config: RunConfig | None, dim_id: str | None,
) -> Callable | None:
    """The ``on_file_done`` cache-writer closure, or None to skip caching.

    Both *run_config* and *dim_id* are required for the synchronous
    cache-write path; legacy callers that omit either get None (no cache is
    written). Imports stay lazy so the cache machinery loads only when the
    path is actually enabled.
    """
    if run_config is None or dim_id is None:
        return None
    from quodeq.analysis.cache.cache_writer import (  # noqa: PLC0415
        CacheWriterSpec,
        build_cache_writer,
    )
    from quodeq.analysis.cache.local import default_cache_root as _dcr  # noqa: PLC0415
    return build_cache_writer(
        CacheWriterSpec.from_run_config(run_config, dim_id, _dcr()),
    )


def _resolve_run_collaborators(
    jsonl_file: Path,
    run_config: RunConfig | None,
    dim_id: str | None,
    event_log: EventLogWriter | None,
    cache_writer: Callable | None,
) -> tuple[EventLogWriter, Callable | None]:
    """Ensure the evidence dir exists, and resolve the event-log/cache-writer
    defaults for the ones the caller left unset."""
    jsonl_file.parent.mkdir(parents=True, exist_ok=True)
    if event_log is None:
        event_log = _build_event_log(jsonl_file.parent.parent)
    if cache_writer is None:
        cache_writer = _build_cache_writer(run_config, dim_id)
    return event_log, cache_writer


def _mark_source_files_done(
    router: FindingsRouter,
    source_file_paths: list[str] | None,
    was_lossy: bool,
    fatal_exc: FatalProviderError | None,
) -> None:
    """Mark every source file done: 'ok' on a clean call, 'error' on a lossy one.

    Clean end-to-end call -> 'ok'; lossy call (model unreachable / network /
    timeout) -> 'error'. The 'error' status is excluded from the cache's
    ok_files set (files still re-dispatch next run), but lets the
    failure-streak breaker and the post-run reachability guard see the
    failure and fail the run loudly.
    """
    if not source_file_paths:
        return
    status = "error" if was_lossy else "ok"
    reason = None
    if fatal_exc is not None:
        reason = f"fatal provider error ({fatal_exc.reason}): {fatal_exc}"
    elif was_lossy:
        reason = "model call failed (unreachable or errored)"
    for path in source_file_paths:
        router.mark_file_done(file=path, status=status, reason=reason)


@dataclass(frozen=True)
class ApiAnalysisRequest:
    """Per-call inputs to ``run_api_analysis``: the prompt, its evidence sink,
    and the enrichment/cache-key context.

    ``dim_id`` and ``dimension`` stay separate fields even though the one
    production caller (``subprocess.py``) always passes ``cfg.dimension`` to
    both -- tests exercise them independently (``dim_id`` keys the cache
    write, ``dimension`` selects compiled standards for enrichment).
    """

    prompt: str
    jsonl_file: Path
    compiled_dir: Path | None = None
    dimension: str | None = None
    work_dir: Path | None = None
    source_file_paths: list[str] | None = None
    run_config: RunConfig | None = None
    dim_id: str | None = None


@dataclass(frozen=True)
class ApiRunnerSeams:
    """Test-injection seams for ``run_api_analysis``: event log, cache
    writer, and the ``FindingsRouter`` factory. ``cache_writer=None`` keeps
    meaning "no cache" (``_resolve_run_collaborators`` checks it via ``is None``).
    """

    event_log: EventLogWriter | None = None
    cache_writer: Callable | None = None
    router_factory: Callable[..., FindingsRouter] = FindingsRouter


def _run_call_and_enrich(
    request: ApiAnalysisRequest, config: ApiRunnerConfig,
) -> tuple[list[dict], bool, FatalProviderError | None, CompiledContext | None]:
    """Call the model, resolve/enrich its findings, and build the router context.

    A fatal provider error (quota/auth/billing) is captured rather than raised
    here -- the caller still needs to write 'error' markers first (the breaker
    and reachability guard rely on them) before re-raising it.
    """
    fatal_exc: FatalProviderError | None = None
    try:
        findings, was_lossy = _call_api(request.prompt, config)
    except FatalProviderError as exc:
        fatal_exc, findings, was_lossy = exc, [], True

    if request.source_file_paths:
        findings = _resolve_file_paths(findings, request.source_file_paths)
    _infer_end_line(findings)

    project_dir, run_dir = _derive_run_paths(request.jsonl_file)
    ctx = _build_router_context(
        request.compiled_dir, request.dimension, request.work_dir, project_dir, run_dir,
    )
    return findings, was_lossy, fatal_exc, ctx


def run_api_analysis(
    *,
    request: ApiAnalysisRequest,
    config: ApiRunnerConfig,
    seams: ApiRunnerSeams = ApiRunnerSeams(),
) -> None:
    """Call the LLM and write findings as JSONL evidence through ``FindingsRouter``.

    Both the CLI/MCP and API paths write per-dim evidence through this one
    sink, which owns atomic writes, dedup/enrichment, and the
    ``mark_file_done`` marker the V2 cache's ``ok_files`` filter reads. See
    ``_mark_source_files_done`` for the marker contract and
    ``_run_call_and_enrich`` for the fatal-provider-error capture.

    ``request.run_config``/``request.dim_id`` enable the cache-write path via
    ``FindingsRouter(on_file_done=...)``. ``seams`` groups the three test
    injection points -- see ``ApiRunnerSeams`` for the ``cache_writer=None``
    contract.
    """
    findings, was_lossy, fatal_exc, ctx = _run_call_and_enrich(request, config)
    _log.debug(
        "API runner: %d findings, lossy=%s, marking %d file(s) as %s",
        len(findings), was_lossy,
        len(request.source_file_paths) if request.source_file_paths else 0,
        "error" if was_lossy else "ok",
    )
    event_log, cache_writer = _resolve_run_collaborators(
        request.jsonl_file, request.run_config, request.dim_id,
        seams.event_log, seams.cache_writer,
    )
    with open(request.jsonl_file, "a", encoding="utf-8") as fh:
        router = seams.router_factory(
            fh, context=ctx, event_log=event_log, on_file_done=cache_writer,
        )
        for f in findings:
            router.receive(f)
        _mark_source_files_done(router, request.source_file_paths, was_lossy, fatal_exc)
    if fatal_exc is not None:
        raise fatal_exc
