import json
from pathlib import Path

import pytest

from quodeq.verifier.eval_harness import (
    EvalCase,
    EvalResult,
    load_eval_cases,
    replay_case,
)
from quodeq.verifier.models import Verdict


def test_load_eval_cases_from_directory(tmp_path: Path):
    case = {
        "id": "di-with-default",
        "manifest_path": "manifest.yaml",
        "finding": {
            "file": "api/app.py",
            "line": 6,
            "category": "flexibility/adaptability",
            "severity": "major",
        },
        "canned_response_path": "response.json",
        "expected_verdict": "false_positive",
    }
    (tmp_path / "case1.json").write_text(json.dumps(case))

    cases = load_eval_cases(tmp_path)
    assert len(cases) == 1
    assert cases[0].id == "di-with-default"
    assert cases[0].expected_verdict == Verdict.FALSE_POSITIVE


def test_replay_case_passes_when_canned_response_matches_expected_verdict(tmp_path: Path):
    response = {
        "checklist": {
            "Q1": {"answer": "yes", "cite": "MANIFEST"},
            "Q2": {"answer": "yes", "cite": None},
            "Q3": {"answer": "yes", "cite": "MANIFEST"},
            "Q4": {"answer": "yes", "cite": "MANIFEST"},
            "Q5": {"answer": "yes", "cite": "MANIFEST"},
        },
        "findings": {
            "default_implementation": {"value": "X", "cite": "MANIFEST"},
            "override_mechanism": {"value": "Y", "cite": "MANIFEST"},
            "abstraction_in_use": {"value": "Z", "cite": "MANIFEST"},
        },
        "confidence": 1.0,
        "evidence_summary": "x",
    }
    case = EvalCase(
        id="t",
        finding={"file": "x", "line": 1, "category": "x"},
        canned_response=response,
        expected_verdict=Verdict.FALSE_POSITIVE,
    )
    result = replay_case(case)
    assert isinstance(result, EvalResult)
    assert result.passed is True
    assert result.actual_verdict == Verdict.FALSE_POSITIVE


def test_replay_case_fails_when_verdict_differs(tmp_path: Path):
    response = {
        "checklist": {
            "Q1": {"answer": "yes", "cite": "MANIFEST"},
            "Q2": {"answer": "yes", "cite": None},
            "Q3": {"answer": "no", "cite": None},
            "Q4": {"answer": "yes", "cite": "MANIFEST"},
            "Q5": {"answer": "yes", "cite": "MANIFEST"},
        },
        "findings": {
            "default_implementation": {"value": None, "cite": None},
            "override_mechanism": {"value": None, "cite": None},
            "abstraction_in_use": {"value": None, "cite": None},
        },
        "confidence": 0.5,
        "evidence_summary": "x",
    }
    case = EvalCase(
        id="t",
        finding={"file": "x", "line": 1, "category": "x"},
        canned_response=response,
        expected_verdict=Verdict.FALSE_POSITIVE,
    )
    result = replay_case(case)
    assert result.passed is False
    assert result.actual_verdict == Verdict.CONFIRMED
