"""API runner for direct LLM evaluation.

Calls LLM APIs directly via the raw OpenAI client and writes findings as
JSONL evidence -- the same format the CLI runner produces via MCP.

``_Finding`` (below) is a lenient short-key variant of the canonical
``Judgment`` (``quodeq.core.events.models``). Local models drop required
fields and balk at long field names under load -- this type's short keys
(``req``/``t``/``w``) and Field descriptions are tuned for that constraint.
The downstream wire-dict → Judgment lift happens via
``quodeq.core.finding_mappings.wire_dict_to_judgment`` after
``FindingEnricher`` maps ``req`` to ``practice_id``.

Requires the ``quodeq[api]`` extra: ``pip install 'quodeq[api]'``
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum as _Enum
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import openai
from pydantic import BaseModel, Field

from quodeq.analysis._drop_stats import record as _record_drop_stats
from quodeq.analysis.mcp.router import CompiledContext, FindingsRouter

if TYPE_CHECKING:
    from quodeq.analysis._types import RunConfig
from quodeq.context.precedent import load_precedent_corpus, load_precedent_fingerprints
from quodeq.context.project_shape import detect_shape
from quodeq.core.standards.refs import load_compiled_requirements
from quodeq.core.standards.refs import load_compiled_refs
from quodeq.shared.url_validation import validate_url_safe

_log = logging.getLogger(__name__)

_OLLAMA_DEFAULT_BASE = "http://localhost:11434/v1"
_OLLAMA_DEFAULT_API_KEY = "ollama"
_OPENAI_API_HOST = "api.openai.com"
_LOCAL_TIMEOUT = httpx.Timeout(connect=10.0, read=500.0, write=30.0, pool=10.0)
_SYSTEM_PROMPT = (
    "You are a code quality evaluator. Quote the offending code into "
    "`snippet` VERBATIM from the source, one or a few contiguous lines, "
    "exact characters, no paraphrase. Set `end_line` to match the last "
    "line of the snippet. In `reason`, state what the code does wrong and "
    "the concrete impact in 1 to 3 sentences. "
    'Return JSON as {"findings": [...]}; an empty array is valid.'
)


# ---------------------------------------------------------------------------
# Pydantic schema for structured LLM output
# ---------------------------------------------------------------------------

class _FindingType(str, _Enum):
    violation = "violation"
    compliance = "compliance"


class _Severity(str, _Enum):
    critical = "critical"
    major = "major"
    minor = "minor"


class _Finding(BaseModel):
    req: str = Field(description="Requirement ID (e.g. P-TIM-1, S-CON-3)")
    t: _FindingType = Field(description="violation or compliance")
    file: str = Field(description="File path relative to repo root")
    line: int = Field(description="1-indexed line number of the offending expression. MUST be > 0.", gt=0)
    end_line: int | None = Field(
        default=None,
        description=(
            "Last line of the offending span. Set this whenever the violation "
            "spans more than one line — both for structural issues (long "
            "function, nesting depth) and for multi-line expressions or "
            "blocks. Omit only when the issue is genuinely a single line. "
            "The server reads the actual source to render the highlighted "
            "snippet from line..end_line; getting end_line right is what "
            "makes the highlight readable."
        ),
    )
    severity: _Severity = Field(default=_Severity.minor)
    vt: str | None = Field(
        default=None,
        description=(
            "Violation type taxonomy code: a short, stable, kebab-case class "
            "of the violation (e.g. 'code-injection', 'hardcoded-secret', "
            "'missing-error-handling'). Reuse the exact same code for every "
            "finding of the same kind so near-duplicates group together."
        ),
    )
    w: str = Field(description="Short title of the finding")
    snippet: str = Field(
        description=(
            "Offending code copied VERBATIM from the source file — exact "
            "characters, no paraphrase, no summarisation. One or a few "
            "contiguous lines: quote enough that the issue is self-evident, "
            "no padding. The number of lines in `snippet` must match the "
            "span from `line` to `end_line` (so end_line - line + 1 == "
            "snippet line count). Required. If you cannot quote the code, "
            "drop the finding."
        ),
        min_length=1,
    )
    reason: str = Field(
        description=(
            "1–3 sentences: state what the quoted code does wrong AS WRITTEN, "
            "and name the concrete impact (what breaks, who is affected, or "
            "what attack/failure it enables). "
            "No hedging ('could', 'might', 'should consider', 'if X were larger')."
        ),
        min_length=1,
    )


# ---------------------------------------------------------------------------
# Config and API call
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApiRunnerConfig:
    """Configuration for a single API runner invocation."""

    model: str
    api_base: str
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int | None = None
    context_size: int = 0


# A dict that fails `_Finding` validation but carries the required, domain-specific
# `req` identifier is a *dropped finding* attempt: counted once for observability,
# then we stop (its own fields are not separate findings, mirroring the valid path).
# A dict that LOOKS like a finding (shares >=2 fields with the schema) but is missing
# `req` is also a dropped attempt -- BUT only when it is a leaf (no nested dict/list
# values). A dict that shares field names yet nests dicts/lists is treated as a
# wrapper and recursed into, so real findings inside it (e.g. {"findings": [...]}) are
# recovered rather than swallowed. The trade-off: a malformed, req-less finding that
# itself nests a container is recursed instead of counted, so it is not tallied in the
# (observability-only) dropped count -- acceptable, since a req-bearing attempt is
# still always counted regardless of nesting.
_DROPPED_FINDING_KEY = "req"
_FINDING_FIELDS = frozenset(_Finding.model_fields)


def _looks_like_finding(node: dict) -> bool:
    """True if *node* shares enough keys with the finding schema to be a finding
    attempt rather than a generic container. Two-field floor avoids false
    positives from generic short keys like ``t``/``w`` appearing alone.
    """
    return len(_FINDING_FIELDS.intersection(node)) >= 2


def _extract_finding_dicts(node: object, sink: list[dict], dropped: list[dict]) -> None:
    """Walk a decoded JSON value, appending any dict that parses as a `_Finding`.

    Recovers findings whether the model emitted them as a bare object, a list,
    a wrapped ``{"findings": [...]}``, or nested somewhere unexpected. Recursion
    stops at a successful ``_Finding`` validation. A dict that fails validation
    but is a finding attempt (carries ``req`` or otherwise looks like a finding)
    is counted as dropped, then recursion stops (mirroring the valid path). Pure
    containers (no finding-like keys) are recursed to recover nested findings.
    """
    if isinstance(node, dict):
        try:
            f = _Finding.model_validate(node)
            sink.append(f.model_dump())
            return
        except (ValueError, KeyError, TypeError):
            if _DROPPED_FINDING_KEY in node:
                dropped.append(node)
                return
            # A finding-shaped LEAF (shares finding fields, no nested containers)
            # that failed validation is a malformed finding attempt -> count it.
            # A dict that merely shares field names while NESTING dicts/lists is a
            # wrapper: fall through and recurse so its real findings are recovered
            # rather than swallowed (counting + stopping here would lose them).
            has_nested = any(isinstance(v, (dict, list)) for v in node.values())
            if _looks_like_finding(node) and not has_nested:
                dropped.append(node)
                return
        for value in node.values():
            _extract_finding_dicts(value, sink, dropped)
    elif isinstance(node, list):
        for item in node:
            _extract_finding_dicts(item, sink, dropped)


def _parse_findings(raw_json: str) -> tuple[list[dict], int]:
    """Parse findings from raw (possibly malformed) model output.

    This is the primary parser, not a fallback. Local models produce several
    failure shapes: bare finding objects concatenated without an array wrapper
    (``{...}{...}``); a complete ``{"findings": [...]}`` wrapper with hedging
    text around it; findings with nested fields like ``req_refs: [{...}]``.

    Strategy: walk the input with ``json.JSONDecoder().raw_decode()`` to find
    every complete top-level JSON value (bracket-aware, so nested structures
    pass through), then harvest anything that validates as a ``_Finding``.

    Returns ``(valid_findings, dropped_count)`` where *dropped_count* is the
    number of finding-shaped dicts that failed validation (for observability).
    """
    decoder = json.JSONDecoder()
    findings: list[dict] = []
    dropped: list[dict] = []
    i = 0
    n = len(raw_json)
    while i < n:
        brace = raw_json.find("{", i)
        bracket = raw_json.find("[", i)
        candidates = [c for c in (brace, bracket) if c >= 0]
        if not candidates:
            break
        start = min(candidates)
        try:
            node, end = decoder.raw_decode(raw_json, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        _extract_finding_dicts(node, findings, dropped)
        i = end
    return findings, len(dropped)


def _call_api(prompt: str, config: ApiRunnerConfig) -> tuple[list[dict], bool]:
    """Call the LLM raw, validate each finding independently, return ``(findings, was_lossy)``.

    ``was_lossy`` is True when the analysis is unreliable: we failed to REACH
    the model (network / timeout), OR the response was truncated by the output
    budget (``finish_reason == "length"``) so findings past the cut are lost. A
    response where only some individual findings were malformed returns
    ``(good_findings, False)`` -- the call succeeded end-to-end, so
    ``run_api_analysis`` may mark files done. Dropped malformed findings are
    logged (count) but do not set ``was_lossy``. See ``run_api_analysis`` for
    the marker contract.

    The OpenAI client owns an httpx connection pool whose sockets count against
    the process FD limit; the ``with`` block closes it so a long scan (one call
    per file) doesn't exhaust the FD soft cap.
    """
    if config.api_base and config.api_base != _OLLAMA_DEFAULT_BASE:
        validate_url_safe(config.api_base, allow_private=True)

    is_openai = _OPENAI_API_HOST in (config.api_base or "")
    extra_body: dict = {}
    if is_openai:
        extra_body["reasoning_effort"] = "none"
    else:
        # Disable chat-template thinking on reasoning-mode local models
        # (Gemma 4, Qwen3); without it they burn 1000s of tokens before the
        # JSON. Ignored by models that don't support thinking.
        extra_body["chat_template_kwargs"] = {"enable_thinking": False}
    ctx_size = config.context_size
    if ctx_size <= 0:
        env_val = os.environ.get("QUODEQ_CONTEXT_SIZE", "").strip()
        if env_val.isdigit():
            ctx_size = int(env_val)
    if ctx_size > 0:
        extra_body["num_ctx"] = ctx_size

    create_kwargs: dict = dict(
        model=config.model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=config.temperature,
    )
    if is_openai:
        # Cloud OpenAI honours JSON-mode; local providers ignore/reject it.
        create_kwargs["response_format"] = {"type": "json_object"}
    if extra_body:
        create_kwargs["extra_body"] = extra_body
    if config.max_tokens is not None:
        create_kwargs["max_tokens"] = config.max_tokens

    timeout = None if is_openai else _LOCAL_TIMEOUT
    _log.debug("Calling %s model=%s (per-finding parse)", config.api_base, config.model)
    start = time.monotonic()
    with openai.OpenAI(
        base_url=config.api_base,
        api_key=config.api_key or _OLLAMA_DEFAULT_API_KEY,
        timeout=timeout,
        # Disable the SDK's internal timeout retries: each waits the full read
        # budget, compounding one timeout into minutes of dead wall time.
        max_retries=0,
    ) as client:
        try:
            response = client.chat.completions.create(**create_kwargs)
        except Exception as exc:
            elapsed = time.monotonic() - start
            if isinstance(exc, (httpx.TimeoutException, openai.APITimeoutError)):
                _log.warning(
                    "Model %s call timed out after %.0fs. Likely causes: "
                    "--n-subagents > 1 with OLLAMA_NUM_PARALLEL=1 (requests "
                    "queue and the second exceeds the timeout), or context "
                    "too large (try QUODEQ_CONTEXT_SIZE).",
                    config.model, elapsed,
                )
            else:
                _log.warning(
                    "Model %s call failed after %.0fs: %s",
                    config.model, elapsed, str(exc)[:300],
                )
            return [], True

    choice = response.choices[0] if response.choices else None
    finish_reason = getattr(choice, "finish_reason", None)
    text = (choice.message.content or "") if choice else ""
    findings, dropped = _parse_findings(text)
    elapsed = time.monotonic() - start

    # Feed the per-run aggregate so the dimension loops can report ONE
    # drop-ratio signal at end of run instead of N scattered per-call lines.
    _record_drop_stats(dropped=dropped, kept=len(findings))

    # A length-truncated response is an incomplete analysis: the model ran out of
    # output budget mid-stream, so findings after the cut are simply gone. Treat
    # it as lossy so run_api_analysis writes an 'error' marker and the file(s)
    # re-dispatch next run, rather than caching a partial result as 'ok'.
    truncated = finish_reason == "length"
    if truncated:
        _log.warning(
            "Model %s response was truncated (finish_reason=length) after %.0fs; "
            "kept %d finding(s) but the analysis is incomplete and will re-dispatch. "
            "Reduce input size or raise the model context window.",
            config.model, elapsed, len(findings),
        )
    if dropped:
        _log.warning(
            "Model %s: dropped %d malformed finding(s) of %d parsed in %.0fs "
            "(kept %d). The call succeeded; malformed findings were discarded.",
            config.model, dropped, dropped + len(findings), elapsed, len(findings),
        )
    _log.debug(
        "Model %s returned %d valid findings in %.0fs (raw bytes: %d)",
        config.model, len(findings), elapsed, len(text),
    )
    return findings, truncated


# ---------------------------------------------------------------------------
# Enrichment and path resolution
# ---------------------------------------------------------------------------

def _infer_end_line(findings: list[dict]) -> None:
    """Derive end_line from snippet line count when the model omits it.

    Small local models often skip end_line, which collapses the dashboard
    highlight to a single line even when the model quoted several lines into
    snippet. If snippet has N>1 lines and end_line is unset, assume the span
    runs from line to line+N-1.
    """
    for f in findings:
        if f.get("end_line"):
            continue
        snippet = f.get("snippet") or ""
        line = f.get("line") or 0
        if line <= 0 or not snippet:
            continue
        n = snippet.count("\n") + 1
        if n > 1:
            f["end_line"] = line + n - 1


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
    """
    if not compiled_dir:
        return None
    try:
        compiled_refs = load_compiled_refs(compiled_dir, dimension) or {}
        compiled_reqs = load_compiled_requirements(compiled_dir, dimension) or {}
        project_shape = detect_shape(work_dir) if work_dir is not None else None
        precedents = load_precedent_fingerprints(project_dir) if project_dir else set()
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
            precedent_fingerprints=precedents,
            precedent_corpus=corpus,
        )
    except Exception as exc:
        _log.warning("Could not build enrichment context: %s -- writing raw", exc)
        return None


def _resolve_file_paths(findings: list[dict], source_paths: list[str]) -> list[dict]:
    """Resolve short filenames to full relative paths."""
    name_to_path: dict[str, str] = {}
    for p in source_paths:
        name = Path(p).name
        name_to_path[name] = p

    for f in findings:
        file_val = f.get("file", "")
        if file_val and "/" not in file_val and file_val in name_to_path:
            f["file"] = name_to_path[file_val]
    return findings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_api_analysis(
    *,
    prompt: str,
    jsonl_file: Path,
    config: ApiRunnerConfig,
    compiled_dir: Path | None = None,
    dimension: str | None = None,
    work_dir: Path | None = None,
    source_file_paths: list[str] | None = None,
    run_config: RunConfig | None = None,
    dim_id: str | None = None,
) -> None:
    """Call the LLM and write findings as JSONL evidence through ``FindingsRouter``.

    Both the CLI/MCP path and this API path write per-dim evidence through
    a single canonical sink (``FindingsRouter``). The router owns:

    - Atomic per-line writes (concurrency-safe with sibling writers).
    - Finding dedup + enrichment via the compiled standards context.
    - The ``mark_file_done`` per-file completion marker that drives the
      V2 cache's ``ok_files`` filter (``analysis/cache/dimension_helpers.py``).

    Marker contract:
        When the API call completes end-to-end (``was_lossy`` is False), every
        file in *source_file_paths* gets an ``ok`` marker -- the call analysed
        them all. Individual malformed findings may have been dropped during
        per-finding parsing (and were logged with a count), but that does not
        invalidate the file: it was analysed, so it should not re-dispatch.
        On a lossy call (network/timeout/unreachable, or a length-truncated
        response, ``was_lossy`` True), every file gets an ``error`` marker
        instead. ``error`` markers
        are excluded from the cache's ``ok_files`` set, so those files still
        re-dispatch on the next run -- but, unlike emitting no marker at all,
        they let the failure-streak breaker trip and the post-run
        reachability guard fail the run loudly when the model is unreachable.

    *source_file_paths* should be the full per-dim file list. When omitted,
    no markers are emitted (preserves caller flexibility but the run will
    not benefit from V2 cache hits across re-runs).

    *run_config* and *dim_id*, when both provided, enable the synchronous
    cache-write path: a closure built from the run's fingerprint inputs is
    passed to ``FindingsRouter(on_file_done=...)`` so every clean ``ok``
    marker writes its per-file cache entry to disk before returning. Legacy
    callers that omit either remain unchanged -- no cache is written.
    """
    findings, was_lossy = _call_api(prompt, config)

    if source_file_paths:
        findings = _resolve_file_paths(findings, source_file_paths)

    _infer_end_line(findings)

    # jsonl_file is `<project_dir>/<run_id>/evidence/<dim>_evidence.jsonl`,
    # so the project directory is its great-grandparent and the run
    # directory its grandparent. Used by the context-enricher pipeline to
    # load prior dismissals as precedents (fingerprints and, when the
    # semantic-precedents flag is on, the embedded corpus).
    project_dir = jsonl_file.parent.parent.parent if jsonl_file else None
    run_dir = jsonl_file.parent.parent if jsonl_file else None
    ctx = _build_router_context(compiled_dir, dimension, work_dir, project_dir, run_dir)

    _log.debug(
        "API runner: %d findings, lossy=%s, marking %d file(s) as %s",
        len(findings), was_lossy,
        len(source_file_paths) if source_file_paths else 0,
        "error" if was_lossy else "ok",
    )

    events_log = jsonl_file.parent.parent / "events.jsonl"

    jsonl_file.parent.mkdir(parents=True, exist_ok=True)
    from quodeq.core.events.writer import EventLogWriter  # noqa: PLC0415
    event_log = EventLogWriter(events_log)

    cache_writer = None
    if run_config is not None and dim_id is not None:
        from quodeq.analysis.cache.cache_writer import build_cache_writer  # noqa: PLC0415
        model_id = (
            run_config.options.subagent_model
            or run_config.options.ai_model
            or "unknown"
        )
        from quodeq.analysis.cache.local import default_cache_root as _dcr  # noqa: PLC0415
        cache_writer = build_cache_writer(
            cache_root=_dcr(),
            src_root=run_config.src,
            standards_dir=run_config.standards_dir,
            dimension=dim_id,
            model_id=model_id,
            language=run_config.language or "",
        )

    with open(jsonl_file, "a", encoding="utf-8") as fh:
        router = FindingsRouter(
            fh, context=ctx, event_log=event_log, on_file_done=cache_writer,
        )
        for f in findings:
            router.receive(f)
        if source_file_paths:
            # Clean end-to-end call -> 'ok'; lossy call (model unreachable /
            # network / timeout) -> 'error'. The 'error' status is excluded
            # from the cache's ok_files set (files still re-dispatch next run),
            # but lets the failure-streak breaker and the post-run
            # reachability guard see the failure and fail the run loudly.
            status = "error" if was_lossy else "ok"
            reason = "model call failed (unreachable or errored)" if was_lossy else None
            for path in source_file_paths:
                router.mark_file_done(file=path, status=status, reason=reason)
