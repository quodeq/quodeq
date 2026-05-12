"""Verifier service layer -- orchestrates one end-to-end verification request.

Plan 3 surface: the Flask routes call `VerifierService.verify_finding(eval_id,
dimension, finding_id)` and get back a `ServiceResult` with the verdict, the
verification ID, the audit-log path, and the structured response.

The service composes three pieces:
  - A finding locator: looks up file/line/category from the existing evaluation
    store (JSONL or SQLite). Injectable so tests can stub it.
  - The resolver (Plan 1): builds the manifest from the located finding.
  - The verifier (Plan 2): renders the prompt, calls Ollama, returns the result.

It then persists the verification record in the per-evaluation SQLite store and
writes the audit-log directory.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from quodeq.resolver import Resolver
from quodeq.resolver.models import FindingInput
from quodeq.verifier.audit_log import write_audit_log
from quodeq.verifier.client import OllamaClient
from quodeq.verifier.models import (
    Verdict,
    VerifierResult,
)
from quodeq.verifier.prompt import SYSTEM_PROMPT_V8, render_user_prompt
from quodeq.verifier.storage import VerificationRecord, VerificationsStore
from quodeq.verifier.verifier import Verifier


_CONTEXT_BEFORE_DEFAULT = 30
_CONTEXT_AFTER_DEFAULT = 30


def _read_cited_line(path: Path, line: int) -> str:
    """Return the raw source at `line` with no numbering, no marker.

    Used as the `snippet` field for the prompt's CLAIM block. Empty string
    if the file is missing or the line is out of bounds.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            return ""
    src = text.splitlines()
    if 0 < line <= len(src):
        return src[line - 1]
    return ""


def _read_source_context(
    path: Path,
    line: int,
    *,
    before: int = _CONTEXT_BEFORE_DEFAULT,
    after: int = _CONTEXT_AFTER_DEFAULT,
) -> str:
    """Return numbered source lines around `line`, with the cited line marked.

    Format per line:
        ">>>  42: <source>" for the cited line
        "    42: <source>" for surrounding lines

    Clipped at file bounds. Encoding errors fall back to lossy utf-8 decode
    so the prompt always has *something* to look at.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_bytes().decode("utf-8", errors="replace")
    src = text.splitlines()
    start = max(1, line - before)
    end = min(len(src), line + after)
    rows = []
    for i in range(start, end + 1):
        marker = ">>>" if i == line else "   "
        rows.append(f"{marker} {i:4d}: {src[i - 1]}")
    return "\n".join(rows)


class FindingNotFound(Exception):
    """The evaluation's finding store didn't contain the requested finding."""


@dataclass
class LocatedFinding:
    """Result of looking a finding up in the existing evaluation store."""

    file: str
    line: int
    category: str
    severity: str
    description: str = ""   # the finding title (short label)
    reason: str = ""        # the "why it's a violation" body (rich prose)


@dataclass
class ServiceResult:
    verification_id: str
    verdict: Verdict
    result: VerifierResult
    audit_log_dir: Path


FindingLocator = Callable[[str, str, str], LocatedFinding | None]


class VerifierService:
    """Glues resolver + verifier + storage + audit log into one entry point."""

    def __init__(
        self,
        evaluations_root: Path,
        finding_locator: FindingLocator,
        project_root_resolver: Callable[[str], Path] | None = None,
        project_root: Path | None = None,
        client: OllamaClient | None = None,
        model: str = "gemma:4",
    ) -> None:
        if project_root_resolver is None and project_root is None:
            raise ValueError("Either project_root_resolver or project_root must be provided")
        if project_root_resolver is None:
            assert project_root is not None  # type narrowing for mypy
            _static = project_root
            project_root_resolver = lambda _eval_id: _static
        self.evaluations_root = evaluations_root
        self.project_root_resolver = project_root_resolver
        self.finding_locator = finding_locator
        self.model = model
        self.client = client
        self._resolvers: dict[str, Resolver] = {}
        self._resolver_lock = threading.Lock()

    def _resolver_for(self, evaluation_id: str) -> Resolver:
        with self._resolver_lock:
            if evaluation_id not in self._resolvers:
                project_root = self.project_root_resolver(evaluation_id)
                resolver = Resolver(project_root=project_root)
                resolver.build_index()
                self._resolvers[evaluation_id] = resolver
            return self._resolvers[evaluation_id]

    def verify_finding(
        self,
        evaluation_id: str,
        dimension: str,
        finding_id: str,
    ) -> ServiceResult:
        located = self.finding_locator(evaluation_id, dimension, finding_id)
        if located is None:
            raise FindingNotFound(
                f"No finding {finding_id!r} in eval {evaluation_id!r} dim {dimension!r}"
            )

        finding = FindingInput(
            file=located.file,
            line=located.line,
            category=located.category,
            severity=located.severity,
            description=located.description,
        )

        resolver = self._resolver_for(evaluation_id)
        manifest = resolver.build_manifest(finding)
        project_root = self.project_root_resolver(evaluation_id)

        finding_dict = {
            "file": located.file,
            "line": located.line,
            "title": located.description,
            "reason": located.reason,
            "snippet": _read_cited_line(
                project_root / located.file, located.line
            ).strip(),
            "enclosing_role": (
                manifest.target_enclosing_function.signature
                if manifest.target_enclosing_function
                else manifest.target_file_role
            ),
        }
        context = _read_source_context(project_root / located.file, located.line)
        user_prompt = render_user_prompt(finding_dict, context)

        verifier = Verifier(
            project_root=project_root,
            client=self.client,
            model=self.model,
        )
        result = verifier.verify(manifest, finding, user_prompt=user_prompt)

        verification_id = str(uuid.uuid4())
        eval_dir = self.evaluations_root / evaluation_id
        store = VerificationsStore(eval_dir / "verifications.db")
        try:
            record = VerificationRecord(
                verification_id=verification_id,
                evaluation_id=evaluation_id,
                dimension=dimension,
                finding_id=finding_id,
                verdict=result.verdict,
                confidence=result.response.confidence,
                evidence_summary=result.response.evidence_summary,
                model=result.model,
                elapsed_ms=result.elapsed_ms,
                created_at=datetime.now(timezone.utc),
            )
            store.insert(record)
        finally:
            store.close()

        audit_root = eval_dir / "verifier"
        raw_response_dict = _result_to_raw_dict(result)
        audit_dir = write_audit_log(
            root=audit_root,
            verification_id=verification_id,
            manifest=manifest,
            system_prompt=SYSTEM_PROMPT_V8,
            user_prompt=user_prompt,
            raw_response=raw_response_dict,
        )

        return ServiceResult(
            verification_id=verification_id,
            verdict=result.verdict,
            result=result,
            audit_log_dir=audit_dir,
        )


def _result_to_raw_dict(result: VerifierResult) -> dict:
    """Serialize the structured verifier response back to its raw JSON form."""
    return {
        "checklist": {
            q: {"answer": a.answer, "cite": a.cite}
            for q, a in result.response.checklist.items()
        },
        "confidence": result.response.confidence,
        "evidence_summary": result.response.evidence_summary,
    }


def _fnv1a32(s: str) -> str:
    """FNV-1a 32-bit hash, hex output. Matches the JS implementation in App.jsx."""
    h = 0x811c9dc5  # FNV offset basis
    for ch in s.encode("utf-8"):
        h ^= ch
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def _compute_finding_id(finding: dict) -> str:
    """Compute the stable composite id for a finding, matching the UI's scheme."""
    file = finding.get("file") or ""
    line = finding.get("line") or 0
    title = finding.get("title") or ""
    return _fnv1a32(f"{file}|{line}|{title}")


def jsonl_finding_locator(evaluations_root: Path) -> FindingLocator:
    """Return a locator that reads findings from the JSONL evaluation store.

    Looks for findings in any of `<evaluations_root>/<eval_id>/*/evaluation/<dimension>.json`.
    The JSON files use the shape `{"findings": [...]}` where each finding has
    `id`, `file`, `line`, `title`, `principle`, `severity` (and others).
    """

    def _locate(evaluation_id: str, dimension: str, finding_id: str) -> LocatedFinding | None:
        eval_dir = evaluations_root / evaluation_id
        if not eval_dir.exists():
            return None
        for run_dir in eval_dir.iterdir():
            if not run_dir.is_dir():
                continue
            dim_file = run_dir / "evaluation" / f"{dimension}.json"
            if not dim_file.exists():
                continue
            try:
                payload = json.loads(dim_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for finding in payload.get("violations") or payload.get("findings") or []:
                # Match either the explicit id (test/synthetic data) or the
                # composite hash (real findings that have no explicit id field).
                if str(finding.get("id")) == finding_id:
                    match = True
                elif _compute_finding_id(finding) == finding_id:
                    match = True
                else:
                    match = False
                if not match:
                    continue
                principle = finding.get("principle") or ""
                title = finding.get("title") or ""
                reason = finding.get("reason") or finding.get("description") or ""
                return LocatedFinding(
                    file=finding.get("file", ""),
                    line=int(finding.get("line", 0) or 0),
                    category=f"{dimension}/{principle}".strip("/"),
                    severity=str(finding.get("severity", "unknown")),
                    description=title,
                    reason=reason,
                )
        return None

    return _locate
