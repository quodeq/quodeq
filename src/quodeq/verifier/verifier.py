"""Public Verifier API."""

from __future__ import annotations

import time
from pathlib import Path

from quodeq.resolver.models import FindingInput, Manifest
from quodeq.verifier.client import OllamaClient
from quodeq.verifier.models import (
    ChecklistAnswer,
    VerifierResponse,
    VerifierResult,
)
from quodeq.verifier.prompt import SYSTEM_PROMPT_V7_2, render_user_prompt
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

    def verify(self, manifest: Manifest, finding: FindingInput) -> VerifierResult:
        user_prompt = render_user_prompt(
            manifest, finding, project_root=self.project_root
        )
        visible_lines = _extract_visible_lines(user_prompt)

        start = time.monotonic()
        raw = self.client.chat(
            system=SYSTEM_PROMPT_V7_2,
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


def _extract_visible_lines(prompt: str) -> set[tuple[str, int]]:
    """Walk the rendered user prompt and collect (file, line) pairs for every
    `L<N> │ …` line under each `[<path> L<a>-<b>]` header.

    The header path is the full manifest-relative path so that model citations
    of the form `"src/foo/bar.py:90"` match an entry in this set when the
    line is visible.
    """
    visible: set[tuple[str, int]] = set()
    current_file: str | None = None
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and "]" in stripped:
            inside = stripped[1:stripped.index("]")]
            # Header format: "<path> L<start>-<end>". The path itself never
            # contains spaces (it's a relative file path); split on the last
            # space to be safe with edge cases.
            if " L" in inside:
                current_file = inside.rsplit(" L", 1)[0]
            else:
                parts = inside.split(" ")
                current_file = parts[0] if parts else None
            continue
        if current_file and line.lstrip().startswith("L"):
            rest = line.lstrip()
            # "L34 │ …"
            num_part = rest[1:].split(" ", 1)[0].split("\t")[0]
            try:
                num = int(num_part)
            except ValueError:
                continue
            visible.add((current_file, num))
    return visible
