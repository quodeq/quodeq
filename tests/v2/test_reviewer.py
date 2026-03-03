from __future__ import annotations

import json

import pytest

from codecompass.v2.engine.reviewer import run_code_review, _build_batch_context, _make_batches
from codecompass.v2.engine.file_sampler import SampledFile
from codecompass.v2.engine.evidence import Judgment


def _sample_practices():
    return {
        "runtime": "python",
        "version": "1.0.0",
        "practices": [
            {
                "id": "py-003",
                "title": "Avoid os.system and shell=True",
                "cwe": 78,
                "dimension": "security",
                "severity": "high",
                "bad": "os.system(f'rm {path}')",
                "good": "subprocess.run(['rm', path])",
                "explanation": "Shell injection risk",
            },
            {
                "id": "py-010",
                "title": "Use parameterized queries",
                "cwe": 89,
                "dimension": "security",
                "severity": "critical",
                "bad": "cursor.execute(f'SELECT * FROM users WHERE id={uid}')",
                "good": "cursor.execute('SELECT * FROM users WHERE id=?', (uid,))",
                "explanation": "SQL injection risk",
            },
        ],
    }


def _sample_files():
    return [
        SampledFile(
            path="src/app.py",
            content="import os\n\ndef run(cmd):\n    os.system(cmd)\n",
            lines=4,
            reason="high_risk_name",
            truncated=False,
        ),
        SampledFile(
            path="src/db.py",
            content="import sqlite3\n\ndef get_user(uid):\n    c.execute(f'SELECT * FROM users WHERE id={uid}')\n",
            lines=4,
            reason="high_risk_name",
            truncated=False,
        ),
    ]


# ── Batching ────────────────────────────────────────────────────────

def test_make_batches():
    files = _sample_files()
    batches = _make_batches(files, batch_size=1)
    assert len(batches) == 2
    assert len(batches[0]) == 1
    assert len(batches[1]) == 1


def test_make_batches_single():
    files = _sample_files()
    batches = _make_batches(files, batch_size=5)
    assert len(batches) == 1
    assert len(batches[0]) == 2


# ── Context building ────────────────────────────────────────────────

def test_build_batch_context():
    ctx = _build_batch_context(
        batch=_sample_files(),
        practices=_sample_practices(),
        analysis_md="Look for injection.",
        dimensions_config={"applies": [{"id": "security", "weight": 1.2}]},
        batch_num=1,
        total_batches=2,
    )
    assert "Batch 1 of 2" in ctx
    assert "py-003" in ctx
    assert "src/app.py" in ctx
    assert "src/db.py" in ctx
    assert "Look for injection" in ctx


# ── Code review with mock AI ────────────────────────────────────────

def test_run_code_review_basic():
    mock_output = "\n".join([
        json.dumps({
            "practice_id": "py-003",
            "verdict": "violation",
            "file": "src/app.py",
            "line": 4,
            "snippet": "os.system(cmd)",
            "severity": "high",
            "reason": "Direct shell execution",
            "dimension": "security",
            "source": "code_review",
        }),
        json.dumps({
            "practice_id": "py-010",
            "verdict": "violation",
            "file": "src/db.py",
            "line": 4,
            "snippet": "c.execute(f'SELECT...')",
            "severity": "critical",
            "reason": "SQL injection via f-string",
            "dimension": "security",
            "source": "code_review",
        }),
    ])

    def mock_ai(prompt):
        return (mock_output, None)

    judgments, dismissed = run_code_review(
        sampled_files=_sample_files(),
        practices=_sample_practices(),
        analysis_md="",
        dimensions_config={"applies": []},
        ai_caller=mock_ai,
    )
    assert len(judgments) == 2
    assert judgments[0].practice_id == "py-003"
    assert judgments[1].practice_id == "py-010"
    assert dismissed == 0


def test_run_code_review_with_dismissed():
    mock_output = json.dumps({
        "practice_id": "py-003",
        "verdict": "dismissed",
    })

    def mock_ai(prompt):
        return (mock_output, None)

    judgments, dismissed = run_code_review(
        sampled_files=_sample_files(),
        practices=_sample_practices(),
        analysis_md="",
        dimensions_config={"applies": []},
        ai_caller=mock_ai,
    )
    assert len(judgments) == 0
    assert dismissed == 1


def test_run_code_review_empty_files():
    judgments, dismissed = run_code_review(
        sampled_files=[],
        practices=_sample_practices(),
        analysis_md="",
        dimensions_config={"applies": []},
    )
    assert judgments == []
    assert dismissed == 0


def test_run_code_review_ai_error_graceful():
    """AI errors on a batch should be skipped gracefully."""
    def mock_ai(prompt):
        return ("", "API error")

    judgments, dismissed = run_code_review(
        sampled_files=_sample_files(),
        practices=_sample_practices(),
        analysis_md="",
        dimensions_config={"applies": []},
        ai_caller=mock_ai,
    )
    assert judgments == []
    assert dismissed == 0


def test_run_code_review_ai_exception_graceful():
    """AI exceptions should be caught per batch."""
    def mock_ai(prompt):
        raise ConnectionError("network down")

    judgments, dismissed = run_code_review(
        sampled_files=_sample_files(),
        practices=_sample_practices(),
        analysis_md="",
        dimensions_config={"applies": []},
        ai_caller=mock_ai,
    )
    assert judgments == []
    assert dismissed == 0


def test_run_code_review_multiple_batches():
    """Each batch gets its own AI call."""
    call_count = 0
    mock_output = json.dumps({
        "practice_id": "py-003",
        "verdict": "compliance",
        "file": "src/app.py",
        "line": 1,
        "reason": "Good pattern",
        "source": "code_review",
    })

    def mock_ai(prompt):
        nonlocal call_count
        call_count += 1
        return (mock_output, None)

    judgments, _ = run_code_review(
        sampled_files=_sample_files(),
        practices=_sample_practices(),
        analysis_md="",
        dimensions_config={"applies": []},
        ai_caller=mock_ai,
        batch_size=1,
    )
    assert call_count == 2
    assert len(judgments) == 2


def test_finding_rule_tagged():
    """Judgments from reviewer should have finding_rule = 'code_review'."""
    mock_output = json.dumps({
        "practice_id": "py-003",
        "verdict": "violation",
        "file": "src/app.py",
        "line": 4,
        "reason": "bad",
    })

    def mock_ai(prompt):
        return (mock_output, None)

    judgments, _ = run_code_review(
        sampled_files=_sample_files(),
        practices=_sample_practices(),
        analysis_md="",
        dimensions_config={"applies": []},
        ai_caller=mock_ai,
    )
    assert judgments[0].finding_rule == "code_review"
