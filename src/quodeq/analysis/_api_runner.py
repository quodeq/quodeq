"""API runner for direct LLM evaluation.

Calls LLM APIs directly via Instructor (Pydantic-based structured output)
and writes findings as JSONL evidence -- the same format the CLI runner
produces via MCP.

``_Finding`` (below) is a lenient short-key variant of the canonical
``Judgment`` (``quodeq.core.events.models``). Local models drop required
fields and balk at long field names under load -- this type's short keys
(``req``/``t``/``w``) and Field descriptions are tuned for that constraint,
so the salvage path stays rare. The downstream wire-dict → Judgment lift
happens via ``quodeq.core.finding_mappings.wire_dict_to_judgment`` after
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
import instructor
import openai
from pydantic import BaseModel, Field

from quodeq.analysis.mcp.router import CompiledContext, FindingsRouter

if TYPE_CHECKING:
    from quodeq.analysis._types import RunConfig
from quodeq.context.precedent import load_precedent_fingerprints
from quodeq.context.project_shape import detect_shape
from quodeq.core.standards.refs import load_compiled_requirements
from quodeq.core.standards.refs import load_compiled_refs
from quodeq.shared.url_validation import validate_url_safe

_log = logging.getLogger(__name__)

_MAX_RETRIES = 1
_OLLAMA_DEFAULT_BASE = "http://localhost:11434/v1"
_OLLAMA_DEFAULT_API_KEY = "ollama"
_OPENAI_API_HOST = "api.openai.com"
_LOCAL_TIMEOUT = httpx.Timeout(connect=10.0, read=500.0, write=30.0, pool=10.0)


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


class _Findings(BaseModel):
    findings: list[_Finding]


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


def _is_timeout_error(exc: BaseException) -> bool:
    """Detect httpx timeouts even when Instructor's retry layer wrapped them.

    Instructor raises ``InstructorRetryException`` when ``max_retries`` is
    exhausted, stashing each underlying error in a ``failed_attempts`` list.
    A bare ``isinstance(exc, httpx.ReadTimeout)`` misses these wrapped cases,
    so timeouts surface as "no findings recovered" instead of the
    timeout-specific WARN that tells the user how to fix it. We duck-type
    ``failed_attempts`` so an Instructor version bump that renames or moves
    the exception class still works.
    """
    if isinstance(exc, (httpx.ReadTimeout, httpx.TimeoutException)):
        return True
    attempts = getattr(exc, "failed_attempts", None) or []
    for attempt in attempts:
        inner = getattr(attempt, "exception", None)
        if isinstance(inner, (httpx.ReadTimeout, httpx.TimeoutException)):
            return True
    return False


def _extract_finding_dicts(node: object, sink: list[dict]) -> None:
    """Walk a decoded JSON value, appending any dict that parses as a `_Finding`.

    Used by ``_salvage_partial_findings`` so we recover findings whether
    the model emitted them as a bare object, a list, a wrapped
    ``{"findings": [...]}``, or nested somewhere unexpected. Recursion
    stops at a successful ``_Finding`` validation (so we don't dive into
    a finding's own fields looking for sub-findings).
    """
    if isinstance(node, dict):
        try:
            f = _Finding.model_validate(node)
            sink.append(f.model_dump())
            return
        except (ValueError, KeyError, TypeError):
            pass
        for value in node.values():
            _extract_finding_dicts(value, sink)
    elif isinstance(node, list):
        for item in node:
            _extract_finding_dicts(item, sink)


def _completion_text(completion: object) -> str | None:
    """Extract ``choices[0].message.content`` from an LLM completion.

    Tolerates both pydantic-model and dict shapes so the helper survives
    openai/instructor version drift. Returns None when the structure
    isn't recognisable -- callers must treat that as "no salvage data
    available here" and continue.
    """
    try:
        choices = getattr(completion, "choices", None)
        if choices is None and isinstance(completion, dict):
            choices = completion.get("choices")
        if not choices:
            return None
        first = choices[0]
        message = getattr(first, "message", None)
        if message is None and isinstance(first, dict):
            message = first.get("message")
        if message is None:
            return None
        content = getattr(message, "content", None)
        if content is None and isinstance(message, dict):
            content = message.get("content")
        return content if isinstance(content, str) else None
    except (AttributeError, IndexError, KeyError, TypeError):
        return None


def _salvage_from_failed_attempts(exc: BaseException) -> list[dict]:
    """Recover findings from Instructor's per-attempt completion data.

    When Pydantic rejects ``list[_Finding]`` because one element is
    missing a required field, the ValidationError message only quotes
    the offending element -- every structurally-valid sibling is lost
    if we salvage from ``str(exc)`` alone. Instructor stashes the raw
    LLM completion on each ``FailedAttempt``, which contains everything
    the model emitted, so walking those gives us a complete view.

    Duck-typed so an Instructor version bump that renames the
    attribute or moves the class still works.
    """
    findings: list[dict] = []
    attempts = getattr(exc, "failed_attempts", None) or []
    for attempt in attempts:
        completion = getattr(attempt, "completion", None)
        if completion is None:
            continue
        text = _completion_text(completion)
        if text:
            findings.extend(_salvage_partial_findings(text))
    return findings


def _salvage_partial_findings(raw_json: str) -> list[dict]:
    """Try to extract valid findings from malformed JSON.

    Local models produce several distinct failure shapes:
    - Bare finding objects concatenated without an array wrapper
      (``{...}{...}``), which trips the JSON parser at "trailing
      characters" after the first object.
    - A complete ``{"findings": [...]}`` wrapper that Instructor still
      rejected for a non-structural reason (extra hedging text, etc).
    - Findings with nested fields like ``req_refs: [{...}]``.

    Strategy: walk the input with ``json.JSONDecoder().raw_decode()`` to
    find every complete top-level JSON value (object or array) regardless
    of nested braces, then recurse into each decoded value harvesting
    anything that validates as a ``_Finding``. ``raw_decode`` is
    bracket-aware so nested structures pass through; the previous regex
    approach (shallow ``{[^{}]*}``) silently dropped any finding with a
    nested field.
    """
    decoder = json.JSONDecoder()
    findings: list[dict] = []
    i = 0
    n = len(raw_json)
    while i < n:
        # Advance to the next plausible JSON start. Skipping non-`{`/`[`
        # chars handles the wrapper text Instructor/Pydantic prepends to
        # the model's raw output ("Invalid JSON: ...", error preambles).
        brace = raw_json.find("{", i)
        bracket = raw_json.find("[", i)
        candidates = [c for c in (brace, bracket) if c >= 0]
        if not candidates:
            break
        start = min(candidates)
        try:
            node, end = decoder.raw_decode(raw_json, start)
        except json.JSONDecodeError:
            # Not a real JSON value at this offset -- advance one char
            # and keep scanning. The decoder is the source of truth for
            # "is this position a complete value"; the brace/bracket
            # scan above is just a cheap pre-filter.
            i = start + 1
            continue
        _extract_finding_dicts(node, findings)
        i = end
    return findings


def _call_api(prompt: str, config: ApiRunnerConfig) -> tuple[list[dict], bool]:
    """Call LLM via Instructor and return ``(findings, was_salvaged)``.

    A clean Instructor return means we know the LLM analysed every file in
    the prompt. If we fall through to the salvage path, the response was
    malformed and we extracted whatever flat finding objects we could --
    we can no longer trust which files were actually completed end-to-end,
    so callers must NOT emit per-file ``mark_file_done: ok`` markers in
    that case. See ``run_api_analysis`` for the marker contract.

    The OpenAI client owns an httpx connection pool whose sockets count
    against the process FD limit. Without an explicit close, a long scan
    (one call per file) accumulates pools until macOS's 256-FD soft cap
    aborts the dimension with EMFILE on the next queue read.
    """
    if config.api_base and config.api_base != _OLLAMA_DEFAULT_BASE:
        validate_url_safe(config.api_base, allow_private=True)

    is_openai = _OPENAI_API_HOST in (config.api_base or "")
    extra_body: dict = {}
    if is_openai:
        extra_body["reasoning_effort"] = "none"
    else:
        # Disable chat-template-driven thinking on reasoning-mode local models
        # (Gemma 4, Qwen3). Without this, the model spends 1000s of tokens on
        # reasoning_content before emitting the JSON we asked for, which can
        # push per-batch latency from seconds into minutes. Unknown to models
        # that don't support thinking — they simply ignore it.
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
        response_model=_Findings,
        messages=[
            {"role": "system", "content": "You are a code quality evaluator. Quote the offending code into `snippet` VERBATIM from the source — one or a few contiguous lines, exact characters, no paraphrase. Set `end_line` to match the last line of the snippet. In `reason`, state what the code does wrong and the concrete impact in 1–3 sentences. Empty `findings` is a valid answer."},
            {"role": "user", "content": prompt},
        ],
        temperature=config.temperature,
        max_retries=_MAX_RETRIES,
    )
    if extra_body:
        create_kwargs["extra_body"] = extra_body
    if config.max_tokens is not None:
        create_kwargs["max_tokens"] = config.max_tokens

    timeout = None if is_openai else _LOCAL_TIMEOUT
    # Local providers (omlx DMG, llamacpp, etc.) don't support structured
    # output constraints. MD_JSON uses prompt engineering instead of
    # response_format, so it works on any provider.
    mode = instructor.Mode.JSON if is_openai else instructor.Mode.MD_JSON
    _log.debug("Calling %s model=%s via Instructor mode=%s", config.api_base, config.model, mode)
    with openai.OpenAI(
        base_url=config.api_base,
        api_key=config.api_key or _OLLAMA_DEFAULT_API_KEY,
        timeout=timeout,
    ) as oa_client:
        client = instructor.from_openai(oa_client, mode=mode)
        start = time.monotonic()
        try:
            result = client.chat.completions.create(**create_kwargs)
            _log.debug("Instructor returned %d findings in %.0fs", len(result.findings), time.monotonic() - start)
            return [f.model_dump() for f in result.findings], False
        except Exception as exc:
            elapsed = time.monotonic() - start
            # Timeouts are unrecoverable -- no JSON to salvage, and the
            # message wouldn't tell the user what's wrong. Call them out
            # explicitly so the failure mode is visible in default INFO logs.
            # Note: when Instructor exhausts retries it wraps the underlying
            # ReadTimeout in InstructorRetryException; ``_is_timeout_error``
            # walks ``failed_attempts`` so wrapped timeouts still surface
            # with the actionable hint rather than as generic failures.
            if _is_timeout_error(exc):
                _log.warning(
                    "Ollama call timed out after %.0fs (model=%s). "
                    "Likely causes: --n-subagents > 1 with OLLAMA_NUM_PARALLEL=1 "
                    "(requests queue and second-in-line exceeds the timeout), "
                    "or context too large (try QUODEQ_CONTEXT_SIZE).",
                    elapsed, config.model,
                )
                return [], True
            # Try Instructor's stashed completions first: when the model
            # emits a valid {"findings":[...]} array but ONE element fails
            # validation (e.g. missing ``reason``), Pydantic's error message
            # only quotes the offending element. The good siblings are
            # invisible in ``str(exc)`` but they are in
            # ``failed_attempts[*].completion.choices[0].message.content``.
            salvaged = _salvage_from_failed_attempts(exc)
            # Fall back to exception-string salvage for older Instructor
            # versions or non-retry exceptions where completion is absent.
            if not salvaged:
                salvaged = _salvage_partial_findings(str(exc))
            if salvaged:
                _log.warning(
                    "Model %s returned malformed JSON after %.0fs -- salvaged %d findings from the response",
                    config.model, elapsed, len(salvaged),
                )
                return salvaged, True
            _log.warning(
                "Model %s call failed after %.0fs, no findings recovered: %s",
                config.model, elapsed, str(exc)[:300],
            )
            return [], True


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
        return CompiledContext(
            compiled_refs=compiled_refs,
            compiled_reqs=compiled_reqs,
            dimension=dimension,
            work_dir=work_dir,
            project_shape=project_shape,
            precedent_fingerprints=precedents,
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
    """Call an LLM API and persist evidence through ``FindingsRouter``.

    Both the CLI/MCP path and this API path write per-dim evidence through
    a single canonical sink (``FindingsRouter``). The router owns:

    - Atomic per-line writes (concurrency-safe with sibling writers).
    - Finding dedup + enrichment via the compiled standards context.
    - The ``mark_file_done`` per-file completion marker that drives the
      V2 cache's ``ok_files`` filter (``analysis/cache/dimension_helpers.py``).

    Marker contract:
        On a clean Instructor return, every file in *source_file_paths* gets
        an ``ok`` marker -- the API call analysed all of them in one shot.
        On the salvage path (malformed JSON, partial recovery) we cannot
        prove which files were actually completed, so no markers are emitted
        and the cache will dispatch all of them on the next run. Same
        guarantee as the CLI path: a file is only ever marked ``ok`` when
        analysis genuinely finished.

    *source_file_paths* should be the full per-dim file list. When omitted,
    no markers are emitted (preserves caller flexibility but the run will
    not benefit from V2 cache hits across re-runs).

    *run_config* and *dim_id*, when both provided, enable the synchronous
    cache-write path: a closure built from the run's fingerprint inputs is
    passed to ``FindingsRouter(on_file_done=...)`` so every clean ``ok``
    marker writes its per-file cache entry to disk before returning. Legacy
    callers that omit either remain unchanged -- no cache is written.
    """
    findings, was_salvaged = _call_api(prompt, config)

    if source_file_paths:
        findings = _resolve_file_paths(findings, source_file_paths)

    _infer_end_line(findings)

    # jsonl_file is `<project_dir>/<run_id>/evidence/<dim>_evidence.jsonl`,
    # so the project directory is its great-grandparent. Used by the
    # context-enricher pipeline to load prior dismissals as precedents.
    project_dir = jsonl_file.parent.parent.parent if jsonl_file else None
    ctx = _build_router_context(compiled_dir, dimension, work_dir, project_dir)

    _log.debug(
        "API runner: %d findings, salvaged=%s, marking %d files",
        len(findings), was_salvaged,
        len(source_file_paths) if source_file_paths and not was_salvaged else 0,
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
        cache_writer = build_cache_writer(
            cache_root=Path.home() / ".quodeq" / "cache" / "results",
            src_root=run_config.src,
            standards_dir=run_config.standards_dir,
            dimension=dim_id,
            model_id=model_id,
            language=run_config.language or "",
        )

    with open(jsonl_file, "a") as fh:
        router = FindingsRouter(
            fh, context=ctx, event_log=event_log, on_file_done=cache_writer,
        )
        for f in findings:
            router.receive(f)
        if not was_salvaged and source_file_paths:
            for path in source_file_paths:
                router.mark_file_done(file=path, status="ok")
