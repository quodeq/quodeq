"""API runner for direct LLM evaluation.

Calls LLM APIs directly via Instructor (Pydantic-based structured output)
and writes findings as JSONL evidence -- the same format the CLI runner
produces via MCP.

Requires the ``quodeq[api]`` extra: ``pip install 'quodeq[api]'``
"""
from __future__ import annotations

import io
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
from quodeq.core.standards.refs import load_compiled_requirements
from quodeq.engine._ref_utils import load_compiled_refs
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
    line: int = Field(default=0, description="Line number")
    severity: _Severity = Field(default=_Severity.minor)
    w: str = Field(description="Short title of the finding")
    reason: str = Field(default="", description="Why this is a violation or compliance")


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


def _call_api(prompt: str, config: ApiRunnerConfig) -> list[dict]:
    """Call LLM via Instructor — returns validated finding dicts.

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
            {"role": "system", "content": "You are a code quality evaluator."},
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
            return [f.model_dump() for f in result.findings]
        except Exception as exc:
            # Try to salvage valid findings from the malformed response
            raw = str(exc)
            salvaged = _salvage_partial_findings(raw)
            if salvaged:
                _log.debug("Instructor validation failed — salvaged %d findings from malformed response", len(salvaged))
                return salvaged
            _log.debug("Instructor validation failed — no findings salvaged: %s", str(exc)[:200])
            return []


# ---------------------------------------------------------------------------
# Enrichment and path resolution
# ---------------------------------------------------------------------------

def _enrich_findings(
    findings: list[dict],
    compiled_dir: Path | None,
    dimension: str | None,
    work_dir: Path | None,
) -> list[dict]:
    """Enrich findings through FindingsRouter (same as MCP path)."""
    if not compiled_dir:
        return findings
    try:
        compiled_refs = load_compiled_refs(compiled_dir, dimension) or {}
        compiled_reqs = load_compiled_requirements(compiled_dir, dimension) or {}
        ctx = CompiledContext(
            compiled_refs=compiled_refs,
            compiled_reqs=compiled_reqs,
            dimension=dimension,
            work_dir=work_dir,
        )

        buf = io.StringIO()
        router = FindingsRouter(buf, context=ctx)
        for f in findings:
            router.receive(f)
        buf.seek(0)
        return [json.loads(line) for line in buf if line.strip()]
    except Exception as exc:
        _log.warning("Could not enrich findings: %s — writing raw", exc)
        return findings


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
    """Call an LLM API and write findings to JSONL."""
    findings = _call_api(prompt, config)

    if source_file_paths:
        findings = _resolve_file_paths(findings, source_file_paths)

    findings = _enrich_findings(findings, compiled_dir, dimension, work_dir)

    _log.debug("Received %d findings from API", len(findings))

    with open(jsonl_file, "a") as fh:
        for finding in findings:
            fh.write(json.dumps(finding) + "\n")
