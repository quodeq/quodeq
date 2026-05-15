"""API runner for direct LLM evaluation.

Calls LLM APIs directly via Instructor (Pydantic-based structured output)
and writes findings as JSONL evidence -- the same format the CLI runner
produces via MCP.

Requires the ``quodeq[api]`` extra: ``pip install 'quodeq[api]'``
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from enum import Enum as _Enum
from pathlib import Path

import instructor
import openai
from pydantic import BaseModel, Field

from quodeq.analysis.mcp.router import CompiledContext, FindingsRouter
from quodeq.context.precedent import load_precedent_fingerprints
from quodeq.context.project_shape import detect_shape
from quodeq.core.standards.refs import load_compiled_requirements
from quodeq.core.standards.refs import load_compiled_refs
from quodeq.shared.url_validation import validate_url_safe

_log = logging.getLogger(__name__)

_MAX_RETRIES = 1
_OLLAMA_DEFAULT_BASE = "http://localhost:11434/v1"
_OLLAMA_DEFAULT_API_KEY = "ollama"


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


def _salvage_partial_findings(raw_json: str) -> list[dict]:
    """Try to extract valid findings from malformed JSON.

    Local models sometimes drop a brace in long arrays, producing invalid
    JSON. We try to parse each object individually.

    Note: the regex ``r'\\{[^{}]*\\}'`` is intentionally shallow — it matches
    single-level (non-nested) JSON objects only.  This is sufficient for
    salvaging malformed local-model output where each finding is a flat
    object, and avoids the complexity of nested-brace matching.
    """
    objects = re.findall(r'\{[^{}]*\}', raw_json)
    findings = []
    for obj_str in objects:
        try:
            f = _Finding.model_validate_json(obj_str)
            findings.append(f.model_dump())
        except (ValueError, KeyError, TypeError):
            continue
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

    extra_body: dict = {"reasoning_effort": "none"}
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
        extra_body=extra_body,
    )
    if config.max_tokens is not None:
        create_kwargs["max_tokens"] = config.max_tokens

    _log.debug("Calling %s model=%s via Instructor", config.api_base, config.model)
    with openai.OpenAI(
        base_url=config.api_base,
        api_key=config.api_key or _OLLAMA_DEFAULT_API_KEY,
    ) as oa_client:
        client = instructor.from_openai(oa_client, mode=instructor.Mode.JSON)
        try:
            result = client.chat.completions.create(**create_kwargs)
            _log.debug("Instructor returned %d findings", len(result.findings))
            return [f.model_dump() for f in result.findings], False
        except Exception as exc:
            # Try to salvage valid findings from the malformed response
            raw = str(exc)
            salvaged = _salvage_partial_findings(raw)
            if salvaged:
                _log.debug("Instructor validation failed — salvaged %d findings from malformed response", len(salvaged))
                return salvaged, True
            _log.debug("Instructor validation failed — no findings salvaged: %s", str(exc)[:200])
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

    jsonl_file.parent.mkdir(parents=True, exist_ok=True)
    with open(jsonl_file, "a") as fh:
        router = FindingsRouter(fh, context=ctx)
        for f in findings:
            router.receive(f)
        if not was_salvaged and source_file_paths:
            for path in source_file_paths:
                router.mark_file_done(file=path, status="ok")
