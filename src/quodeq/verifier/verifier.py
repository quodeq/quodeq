"""Public Verifier API."""

from __future__ import annotations

import re
import time
from pathlib import Path

from quodeq.resolver.models import FindingInput, Manifest
from quodeq.verifier.client import OllamaClient
from quodeq.verifier.models import (
    ChecklistAnswer,
    VerifierResponse,
    VerifierResult,
)
from quodeq.verifier.prompt import SYSTEM_PROMPT_V8
from quodeq.verifier.schema import RESPONSE_SCHEMA
from quodeq.verifier.validate import enforce_citation_validity
from quodeq.verifier.verdict import compute_verdict


class Verifier:
    """Orchestrates render → call → validate → compute for a single finding."""

    def __init__(
        self,
        project_root: Path | None = None,
        client: OllamaClient | None = None,
        model: str = "gemma:4",
        temperature: float = 0.0,
        seed: int = 0,
    ) -> None:
        self.project_root = project_root
        self.client = client or OllamaClient()
        self.model = model
        self.temperature = temperature
        self.seed = seed

    def verify(self, manifest: Manifest, finding: FindingInput, user_prompt: str | None = None) -> VerifierResult:
        if user_prompt is None:
            # Backward compat for any direct test caller; normally the service
            # layer renders the prompt and passes it in.
            from quodeq.verifier.prompt import render_user_prompt as _render
            from quodeq.verifier.service import _read_source_context
            # Fall back to a thin best-effort render — used only in unit tests
            # that call Verifier.verify directly.
            project_root = self.project_root or Path.cwd()
            source_path = project_root / finding.file
            try:
                context = _read_source_context(source_path, finding.line)
            except FileNotFoundError:
                context = "(source unavailable in this test fixture)"
            finding_dict = {
                "file": finding.file,
                "line": finding.line,
                "title": finding.description,
                "reason": "",
                "snippet": finding.cited_text or "",
                "enclosing_role": (
                    manifest.target_enclosing_function.signature
                    if manifest.target_enclosing_function
                    else manifest.target_file_role
                ),
            }
            user_prompt = _render(finding_dict, context)
        visible_lines = _extract_visible_lines(user_prompt)

        start = time.monotonic()
        raw = self.client.chat(
            system=SYSTEM_PROMPT_V8,
            user=user_prompt,
            schema=RESPONSE_SCHEMA,
            model=self.model,
            temperature=self.temperature,
            seed=self.seed,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)

        response = parse_verifier_response(raw)
        cleaned = enforce_citation_validity(response, visible_lines)
        verdict = compute_verdict(cleaned)

        return VerifierResult(
            verdict=verdict,
            response=cleaned,
            consistency_warnings=[],
            model=self.model,
            elapsed_ms=elapsed_ms,
        )


def parse_verifier_response(raw: dict) -> VerifierResponse:
    checklist = {
        qid: ChecklistAnswer(answer=ans["answer"], cite=ans["cite"])
        for qid, ans in raw["checklist"].items()
    }
    return VerifierResponse(
        checklist=checklist,
        confidence=raw["confidence"],
        evidence_summary=raw["evidence_summary"],
    )


_FILE_HEADER_RE = re.compile(r"^\s*file:\s*(.+\S)\s*$")
_NUMBERED_LINE_RE = re.compile(r"^(?:>>>|\s{3})\s+(\d+):\s")


def _extract_visible_lines(prompt: str) -> set[tuple[str, int]]:
    """Walk the v8-rendered user prompt and collect (file, line) pairs for
    every numbered context row.

    The v8 prompt has the form::

        EVIDENCE
          file: src/foo/bar.py
          cited line (L42): TIMEOUT = 30
          context (numbered, cited line marked with >>>):
              40: import requests
              41:
        >>>   42: TIMEOUT = 30
              43:

    We identify the active file from the `  file: <path>` line and then
    accept every subsequent numbered row (with or without the `>>>` marker)
    as visible. Citations like ``"src/foo/bar.py:42"`` will match an entry
    in the returned set; anything outside the shown context window is
    downgraded by ``enforce_citation_validity``.
    """
    visible: set[tuple[str, int]] = set()
    current_file: str | None = None
    for raw in prompt.splitlines():
        m = _FILE_HEADER_RE.match(raw)
        if m:
            current_file = m.group(1)
            continue
        if current_file is None:
            continue
        n = _NUMBERED_LINE_RE.match(raw)
        if not n:
            continue
        try:
            visible.add((current_file, int(n.group(1))))
        except ValueError:
            continue
    return visible
