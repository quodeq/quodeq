"""S-CON-1 deterministic checker: one masked violation per secret."""
from __future__ import annotations

from quodeq.core.checks.hardcoded_secrets import REQ, check_hardcoded_secrets
from tests.core._fake_secrets import AWS_KEY, GITHUB_TOKEN


def test_one_critical_violation_per_secret_with_masked_snippet():
    sources = [
        ("app/config.py", f"import os\nAWS = '{AWS_KEY}'\nGH = '{GITHUB_TOKEN}'\n"),
        ("app/clean.py", "x = 1\n"),
    ]
    judgments = check_hardcoded_secrets(sources, dimension="security")

    assert [(j.file, j.line, j.req, j.verdict) for j in judgments] == [
        ("app/config.py", 2, REQ, "violation"),
        ("app/config.py", 3, REQ, "violation"),
    ]
    assert {j.severity for j in judgments} == {"critical"}
    assert {j.violation_type for j in judgments} == {"hardcoded-secret"}
    assert judgments[0].snippet == "AWS = '<REDACTED:aws_access_key>'"
    assert all(AWS_KEY not in (j.snippet + j.reason + j.title) for j in judgments)


def test_a_clean_project_emits_nothing():
    """Violations only: the model still judges S-CON-1 for the rest."""
    assert check_hardcoded_secrets([("a.py", "x = 1\n")], dimension="security") == []
