"""Empirical regression suite for the v8 prompt.

Runs each canonical fixture against a live Gemma 4 e4b at temperature=0 and
asserts ground-truth verdict. The single-run-per-fixture default keeps the
suite under 1 minute. To stress-test prompt revisions, override
EMPIRICAL_RUNS_PER_FIXTURE=5 (or higher) in the environment.

Skipped by default. Opt in with:
    pytest tests/verifier/test_empirical.py -m empirical -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from quodeq.verifier.client import OllamaClient
from quodeq.verifier.prompt import SYSTEM_PROMPT_V8, render_user_prompt
from quodeq.verifier.schema import RESPONSE_SCHEMA
from quodeq.verifier.verdict import compute_verdict
from quodeq.verifier.verifier import parse_verifier_response

from tests.verifier.fixtures.empirical_fixtures import EMPIRICAL_FIXTURES


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL = os.environ.get("QUODEQ_EMPIRICAL_MODEL", "gemma4:e4b")
RUNS_PER_FIXTURE = int(os.environ.get("EMPIRICAL_RUNS_PER_FIXTURE", "1"))


def _read_context(path: Path, line: int, before: int, after: int) -> str:
    src = path.read_text(encoding="utf-8").splitlines()
    start = max(1, line - before)
    end = min(len(src), line + after)
    rows = []
    for i in range(start, end + 1):
        marker = ">>>" if i == line else "   "
        rows.append(f"{marker} {i:4d}: {src[i - 1]}")
    return "\n".join(rows)


@pytest.mark.empirical
@pytest.mark.parametrize("fixture", EMPIRICAL_FIXTURES, ids=lambda f: f["id"])
def test_v8_prompt_matches_ground_truth(fixture):
    """Run the fixture through a live Ollama and assert the ground-truth verdict.

    Defaults to one run per fixture. Set EMPIRICAL_RUNS_PER_FIXTURE=5 to test
    stability across seeds.
    """
    client = OllamaClient()
    try:
        verdicts = []
        for seed in range(RUNS_PER_FIXTURE):
            context = _read_context(
                PROJECT_ROOT / fixture["file"], fixture["line"],
                before=fixture["context_before"], after=fixture["context_after"],
            )
            user_prompt = render_user_prompt(fixture, context)
            raw = client.chat(
                system=SYSTEM_PROMPT_V8,
                user=user_prompt,
                schema=RESPONSE_SCHEMA,
                model=MODEL,
                temperature=0.0,
                seed=seed,
            )
            response = parse_verifier_response(raw)
            verdicts.append(compute_verdict(response).value)
        # All runs must converge on ground truth.
        assert all(v == fixture["ground_truth"] for v in verdicts), (
            f"Fixture {fixture['id']}: expected {fixture['ground_truth']!r}, got {verdicts!r}"
        )
    finally:
        client.close()
