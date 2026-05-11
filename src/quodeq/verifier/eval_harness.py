"""Replay-based eval harness.

An EvalCase pins a canned model response and an expected verdict. The harness
computes the verdict from the canned response and asserts it matches the
expectation. Used to catch regressions in the verdict computer, citation
validator, or the verdict rule itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quodeq.verifier.models import Verdict
from quodeq.verifier.verifier import _parse_response
from quodeq.verifier.verdict import compute_verdict


@dataclass
class EvalCase:
    id: str
    finding: dict[str, Any]
    canned_response: dict[str, Any]
    expected_verdict: Verdict


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    expected_verdict: Verdict
    actual_verdict: Verdict
    note: str = ""


def load_eval_cases(directory: Path) -> list[EvalCase]:
    """Load all .json eval cases from a directory.

    Each file is expected to be a JSON object with:
      - id (str)
      - finding (dict)
      - canned_response_path (str, relative to the case file)
      - expected_verdict (str: "false_positive" | "confirmed" | "inconclusive")
    """
    cases: list[EvalCase] = []
    for path in sorted(directory.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        canned_response: dict[str, Any]
        if "canned_response" in spec:
            canned_response = spec["canned_response"]
        elif "canned_response_path" in spec:
            response_path = path.parent / spec["canned_response_path"]
            if response_path.exists():
                canned_response = json.loads(response_path.read_text(encoding="utf-8"))
            else:
                canned_response = {}
        else:
            canned_response = {}
        cases.append(
            EvalCase(
                id=spec["id"],
                finding=spec["finding"],
                canned_response=canned_response,
                expected_verdict=Verdict(spec["expected_verdict"]),
            )
        )
    return cases


def replay_case(case: EvalCase) -> EvalResult:
    """Compute the verdict from the canned response and compare to expected."""
    response = _parse_response(case.canned_response)
    actual = compute_verdict(response)
    return EvalResult(
        case_id=case.id,
        passed=(actual == case.expected_verdict),
        expected_verdict=case.expected_verdict,
        actual_verdict=actual,
    )
