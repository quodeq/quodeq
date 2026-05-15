"""FindingEnricher: transforms raw finding args into an enriched finding dict.

Owns all confidence-downweight heuristics, standards lookups (principle,
dimension, req_refs), and code-snippet extraction.  FindingsRouter delegates
all transformation here and keeps only routing concerns (dedup, I/O, events).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from quodeq.analysis.mcp.enrichment import enrich_code
from quodeq.analysis.mcp.ref_scoring import select_best_refs
from quodeq.context.path_role import NON_PROD_ROLES, path_role
from quodeq.context.precedent import fingerprint as _precedent_fingerprint
from quodeq.context.project_shape import Deployment, ProjectShape

_FINDING_SCHEMA_VERSION = 1
_NON_PROD_DOWNWEIGHT = 50
_SHAPE_DOWNWEIGHT = 40
_PRECEDENT_DOWNWEIGHT = 25

_HOSTED_SERVICE_KEYWORDS: tuple[str, ...] = (
    "concurrent caller", "concurrent callers", "concurrent request",
    "concurrent requests", "thread block", "blocks the thread",
    "blocks thread", "blocks the event loop", "blocks the request thread",
    "distributed state", "distributed system", "distributed lock",
    "multi-tenant", "multitenant", "tenant isolation",
    "rate limit", "rate-limit", "rate limiting",
    "ddos", "denial of service", "denial-of-service",
    "horizontal scaling", "horizontal scale",
)


@runtime_checkable
class FileReader(Protocol):
    """Abstraction for reading source file content."""
    def __call__(self, path: Path) -> str: ...


@dataclass
class CompiledContext:
    """Grouped compiled-standards data for finding enrichment."""
    compiled_refs: dict[str, list[dict]] = field(default_factory=dict)
    compiled_reqs: dict[str, dict] = field(default_factory=dict)
    req_to_dim: dict[str, str] = field(default_factory=dict)
    dimension: str | None = None
    work_dir: Path | None = None
    project_shape: ProjectShape | None = None
    precedent_fingerprints: set[str] = field(default_factory=set)


def _apply_path_role_downweight(finding: dict[str, object]) -> None:
    """Lower confidence to 50 when the finding lives on a non-prod path.

    Skipped when the LLM emitted an explicit confidence below 100 and for
    compliance findings (downweighting "code is fine" makes no sense).
    """
    if finding.get("t") != "violation":
        return
    role = path_role(finding.get("file"))
    if role not in NON_PROD_ROLES:
        return
    existing = finding.get("confidence")
    if existing is None or existing == 100:
        finding["confidence"] = _NON_PROD_DOWNWEIGHT


def _shape_irrelevant_to_hosted_service(shape: ProjectShape | None) -> bool:
    """True when the project clearly isn't a hosted multi-tenant service."""
    if shape is None:
        return False
    if shape.deployment in (Deployment.DESKTOP, Deployment.LIBRARY):
        return True
    if shape.deployment is Deployment.CLI and shape.is_single_user:
        return True
    return False


def _apply_shape_downweight(
    finding: dict[str, object], shape: ProjectShape | None,
) -> None:
    """Downweight findings that assume a hosted service when the project isn't one."""
    if finding.get("t") != "violation":
        return
    if not _shape_irrelevant_to_hosted_service(shape):
        return
    haystack_parts: list[str] = []
    for key in ("reason", "w", "title"):
        val = finding.get(key)
        if isinstance(val, str):
            haystack_parts.append(val.lower())
    haystack = " ".join(haystack_parts)
    if not any(kw in haystack for kw in _HOSTED_SERVICE_KEYWORDS):
        return
    existing = finding.get("confidence")
    if existing is None or existing == 100:
        finding["confidence"] = _SHAPE_DOWNWEIGHT


def _apply_precedent_downweight(
    finding: dict[str, object], fingerprints: set[str] | None,
) -> None:
    """Drop confidence to ~25 when this finding's fingerprint matches a prior dismissal."""
    if not fingerprints:
        return
    if finding.get("t") != "violation":
        return
    req = finding.get("req")
    snippet = finding.get("snippet")
    fp = _precedent_fingerprint(
        req if isinstance(req, str) else None,
        snippet if isinstance(snippet, str) else None,
    )
    if fp is None or fp not in fingerprints:
        return
    existing = finding.get("confidence")
    if existing is None or existing == 100:
        finding["confidence"] = _PRECEDENT_DOWNWEIGHT


def _default_read_file(path: Path) -> str:
    return path.read_text()


class FindingEnricher:
    """Transforms raw finding args into a fully enriched finding dict.

    Fills principle, dimension, and req_refs from compiled standards; attaches
    code snippet and context from source files; and applies the three confidence
    downweight heuristics (path role, project shape, dismissal precedents).
    """

    def __init__(
        self,
        context: CompiledContext,
        file_reader: FileReader | None = None,
    ) -> None:
        self._refs = context.compiled_refs
        self._reqs = context.compiled_reqs
        self._req_to_dim = context.req_to_dim
        self._dimension = context.dimension
        self._work_dir = context.work_dir
        self._project_shape = context.project_shape
        self._precedent_fingerprints = context.precedent_fingerprints
        self._read_file: Callable[[Path], str] = file_reader or _default_read_file

    def dedup_key(self, args: dict) -> tuple:
        """Compute the deduplication key for a raw finding args dict."""
        p = args.get("p")
        req = args.get("req")
        if not p and req and req in self._reqs:
            p = self._reqs[req]["principle"]
        return (p, args.get("file"), args.get("line"), args.get("t"))

    def enrich(self, args: dict) -> dict:
        """Return a fully enriched finding dict built from *args*."""
        req = args.get("req")

        finding: dict = {"schema_version": _FINDING_SCHEMA_VERSION}
        finding.update({k: v for k, v in args.items() if v is not None})

        if not args.get("p") and req and req in self._reqs:
            finding["p"] = self._reqs[req]["principle"]

        if not args.get("d"):
            if req and req in self._req_to_dim:
                finding["d"] = self._req_to_dim[req]
            elif self._dimension:
                finding["d"] = self._dimension

        if req and req in self._refs:
            finding["req_refs"] = select_best_refs(
                self._refs[req], args.get("w", ""), args.get("reason", ""),
            )

        enrich_code(finding, self._work_dir, self._read_file)
        _apply_path_role_downweight(finding)
        _apply_shape_downweight(finding, self._project_shape)
        _apply_precedent_downweight(finding, self._precedent_fingerprints)

        return finding
