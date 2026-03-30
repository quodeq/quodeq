"""Shared data class and helpers for violation/compliance parsing."""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.core.types import Finding, ReqRef


@dataclass(frozen=True)
class ViolationContext:
    """Shared context for violation/compliance parsing."""
    project: str
    run_id: str
    dimension: str


@dataclass(frozen=True)
class FindingSpec:
    """Input fields for building a normalized finding dict."""
    principle: str | None
    file: str | None = None
    line: int | str | None = None
    title: str | None = None
    reason: str | None = None
    snippet: str | None = None
    severity: str | None = None
    cwe: int | str | None = None
    req: str | None = None
    req_refs: list[dict] | None = None
    context: str | None = None
    include_severity: bool = True


def build_finding_base(spec: FindingSpec) -> Finding:
    """Build the core fields shared by all finding/violation normalizers.

    Used by both ``violations_parsing`` (JSONL/stream) and ``json_parser``
    (evaluation JSON) to avoid duplicating the same field assembly (CWE-1041).
    """
    req_refs: list[ReqRef] = []
    if spec.req_refs:
        req_refs = [
            ReqRef(label=ref.get("label", ""), url=ref.get("url", ""))
            for ref in spec.req_refs
        ]
    return Finding(
        principle=spec.principle,
        file=spec.file,
        line=spec.line,
        title=spec.title,
        reason=spec.reason,
        snippet=spec.snippet,
        severity=(spec.severity or "minor") if spec.include_severity else "minor",
        cwe=spec.cwe if spec.cwe else None,
        req=spec.req if spec.req else None,
        req_refs=req_refs,
        context=spec.context if spec.context else None,
    )


def format_file_line(file: str | None, line: int | str | None) -> str | None:
    """Format a ``file:line`` string, returning *file* alone when *line* is absent."""
    if file and line:
        return f"{file}:{line}"
    return file
