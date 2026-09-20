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
from quodeq.analysis.mcp.precedent_downweight import (
    UNSET_SCORE,
    apply_precedent_downweight,
    precedent_scores as _compute_precedent_scores,
    notify_precedent_match,
)
from quodeq.analysis.mcp.ref_scoring import select_best_refs
from quodeq.analysis.mcp.schemas import FINDING_TYPE_VIOLATION
from quodeq.analysis.mcp.severity_gates import apply_severity_gates
from quodeq.context.path_role import NON_PROD_ROLES, path_role
from quodeq.context.precedent import PrecedentCorpus
from quodeq.context.project_shape import Deployment, ProjectShape
from quodeq.context.trust_model import TrustModel
from quodeq.core.constants import FULL_CONFIDENCE
from quodeq.core.observability import NULL_LOG, LogSink

_FINDING_SCHEMA_VERSION = 1
# These downweights set `confidence`, a UI/triage signal ONLY: confidence drives
# the dashboard's "Low confidence" grouping and does NOT affect the grade (it is
# excluded from the scoring fields -- see _report_constants._VIOLATION_FIELDS and
# #640). Severity, set by the analysis LLM and enforced by the provenance gate
# (#639), is the lever that moves the score.
_NON_PROD_DOWNWEIGHT = 50
_SHAPE_DOWNWEIGHT = 40

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
    def __call__(self, path: Path) -> str:
        """Return the text of *path* for snippet extraction."""
        ...


@dataclass
class CompiledContext:
    """Grouped compiled-standards data for finding enrichment."""
    compiled_refs: dict[str, list[dict]] = field(default_factory=dict)
    compiled_reqs: dict[str, dict] = field(default_factory=dict)
    req_to_dim: dict[str, str] = field(default_factory=dict)
    dimension: str | None = None
    work_dir: Path | None = None
    project_shape: ProjectShape | None = None
    trust_model: TrustModel | None = None
    precedent_fingerprints: set[str] = field(default_factory=set)
    precedent_corpus: PrecedentCorpus | None = None
    # Called with the enriched finding on an EXACT precedent match, so the
    # composition root can record a dismissal for it (#1208). Never for the
    # semantic tier. Optional: None keeps precedent a confidence-only signal.
    on_precedent_match: Callable[[dict], None] | None = None


def _apply_path_role_downweight(finding: dict[str, object]) -> None:
    """Lower confidence to 50 when the finding lives on a non-prod path.

    Skipped when the LLM emitted an explicit confidence below 100 and for
    compliance findings (downweighting "code is fine" makes no sense).
    """
    if finding.get("t") != FINDING_TYPE_VIOLATION:
        return
    role = path_role(finding.get("file"))
    if role not in NON_PROD_ROLES:
        return
    existing = finding.get("confidence")
    if existing is None or existing == FULL_CONFIDENCE:
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
    if finding.get("t") != FINDING_TYPE_VIOLATION:
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
    if existing is None or existing == FULL_CONFIDENCE:
        finding["confidence"] = _SHAPE_DOWNWEIGHT


def _default_read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
        *, log: LogSink = NULL_LOG,
    ) -> None:
        self._refs = context.compiled_refs
        self._reqs = context.compiled_reqs
        self._req_to_dim = context.req_to_dim
        self._dimension = context.dimension
        self._work_dir = context.work_dir
        self._project_shape = context.project_shape
        self._trust_model = context.trust_model
        self._precedent_fingerprints = context.precedent_fingerprints
        self._precedent_corpus = context.precedent_corpus
        self._on_precedent_match = context.on_precedent_match
        self._log = log
        base_reader: Callable[[Path], str] = file_reader or _default_read_file
        self._file_cache: dict[Path, str] = {}

        def _cached_read_file(path: Path) -> str:
            cached = self._file_cache.get(path)
            if cached is None:
                cached = base_reader(path)
                self._file_cache[path] = cached
            return cached

        self._read_file: Callable[[Path], str] = _cached_read_file

    def dedup_key(self, args: dict) -> tuple:
        """Compute the deduplication key for a raw finding args dict."""
        p = args.get("p")
        req = args.get("req")
        if not p and req and req in self._reqs:
            p = self._reqs[req]["principle"]
        return (p, args.get("file"), args.get("line"), args.get("t"))

    def _resolve_finding_dimension(
        self, finding: dict, args: dict, req: str | None,
    ) -> None:
        """Reroute *finding*'s dimension (in place) per its requirement.

        The requirement is authoritative for a finding's dimension. When a
        requirement maps to a dimension (multi-dimension scans populate
        req_to_dim across standards), use it even if the model declared a
        different dimension -- this reroutes a misfiled finding to where it is
        actually scored, rather than letting a, say, security issue land under
        maintainability. Falls back to the model's value, then the scanned
        dimension. (An unresolvable requirement that cannot be rerouted is
        quarantined downstream at principle grouping.)
        """
        req_dim = self._req_to_dim.get(req) if req else None
        declared = args.get("d")
        if req_dim:
            if declared and declared != req_dim:
                self._log.warning(
                    f"Rerouting finding from declared dimension {declared!r} to "
                    f"{req_dim!r} per requirement {req!r} "
                    f"(severity={args.get('severity')}, file={args.get('file')})"
                )
            finding["d"] = req_dim
        elif not declared and self._dimension:
            finding["d"] = self._dimension

    def _from_standards(self, args: dict) -> dict:
        """The finding dict *args* maps onto, with its standards-derived fields.

        First stage of the pipeline: no source file is read and no downweight
        is applied yet, so the dict is not usable as a finding on its own.
        """
        req = args.get("req")

        finding: dict = {"schema_version": _FINDING_SCHEMA_VERSION}
        finding.update({k: v for k, v in args.items() if v is not None})

        # Keep the model's tag exactly as emitted. PR B maps `vt` onto the
        # taxonomy; `vt_raw` is what the unmapped-types report and alias
        # curation read. Absent when the model sent no tag.
        if args.get("vt"):
            finding["vt_raw"] = str(args["vt"])

        if not args.get("p") and req and req in self._reqs:
            finding["p"] = self._reqs[req]["principle"]

        self._resolve_finding_dimension(finding, args, req)

        if req and req in self._refs:
            finding["req_refs"] = select_best_refs(
                self._refs[req], args.get("w", ""), args.get("reason", ""),
            )
        return finding

    def _before_precedent(self, finding: dict) -> None:
        """Attach code context and apply the two content-independent downweights.

        Runs before the precedent tier on purpose: ``enrich_code`` replaces the
        model's quoted snippet with the source-derived window, and that window
        is what the precedent corpus was built from. Scoring a precedent before
        this ran embeds a different text than the corpus holds.
        """
        enrich_code(finding, self._work_dir, self._read_file)
        _apply_path_role_downweight(finding)
        _apply_shape_downweight(finding, self._project_shape)

    def _after_precedent(
        self, finding: dict, precedent_score: float | None = UNSET_SCORE,
    ) -> None:
        """Apply the precedent downweight and the severity gates in place.

        Gates the LIVE path only: this runs once per freshly-dispatched
        finding, before it ever reaches the cache. A cached finding replayed on
        a later run does NOT come back through here -- cache replay bypasses
        enrich() entirely and writes straight to the per-dim JSONL, and a
        deterministic checker never comes through here at all. Those two sinks
        (dimension_runner._write_findings, checks.runner) call the same helper
        for the same reason. Every call site is required: this one gates what
        the model just emitted, the others gate what a warm cache is about to
        replay and what a checker just computed, and skipping any one leaves a
        class of findings ungated. See severity_gates.py for why the sequence
        lives there rather than being repeated here.
        """
        tier = apply_precedent_downweight(
            finding, self._precedent_fingerprints, self._precedent_corpus,
            score=precedent_score, log=self._log,
        )
        apply_severity_gates(finding, self._trust_model)
        if tier == "exact":
            notify_precedent_match(self._on_precedent_match, finding, log=self._log)

    def enrich(self, args: dict, *, precedent_score: float | None = UNSET_SCORE) -> dict:
        """Return a fully enriched finding dict built from *args*.

        *precedent_score* lets a caller that already ran the batch semantic
        lookup (``precedent_scores``) skip a second ``corpus.match`` call.
        """
        finding = self._from_standards(args)
        self._before_precedent(finding)
        self._after_precedent(finding, precedent_score)
        return finding

    def enrich_many(self, findings: list[dict]) -> list[dict]:
        """Enrich a batch with one batched precedent lookup for all of them.

        Same per-finding step order as ``enrich``; only the precedent tier is
        shared, and it runs on the ENRICHED dicts so the embedded text is the
        one the corpus was built from.
        """
        enriched = [self._from_standards(args) for args in findings]
        for finding in enriched:
            self._before_precedent(finding)
        scores = self.precedent_scores(enriched)
        for finding, score in zip(enriched, scores):
            self._after_precedent(finding, score)
        return enriched

    def precedent_scores(self, findings: list[dict]) -> list[float | None]:
        """Best-effort semantic precedent score per finding, one embed call.

        None for a finding that skips the lookup and for every finding when
        no precedent corpus is configured.
        """
        return _compute_precedent_scores(
            self._precedent_corpus, self._precedent_fingerprints, findings,
        )
