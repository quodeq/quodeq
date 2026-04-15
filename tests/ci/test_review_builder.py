import json


def test_violation_to_review_comment():
    from quodeq.ci.review_builder import violation_to_comment

    violation = {
        "file": "src/auth/login.py",
        "line": 42,
        "end_line": 42,
        "title": "SQL injection risk",
        "reason": "User input passed directly to query without parameterization.",
        "severity": "critical",
        "req": "V5.3.4",
    }
    comment = violation_to_comment(violation)
    assert comment["path"] == "src/auth/login.py"
    assert comment["line"] == 42
    assert "critical" in comment["body"].lower()
    assert "SQL injection" in comment["body"]


def test_violation_without_line_becomes_file_level():
    from quodeq.ci.review_builder import violation_to_comment

    violation = {
        "file": "src/api/handler.py",
        "line": None,
        "end_line": None,
        "title": "Missing input validation",
        "reason": "Request payload used without schema validation.",
        "severity": "high",
        "req": "V5.1.1",
    }
    comment = violation_to_comment(violation)
    assert comment["path"] == "src/api/handler.py"
    assert "line" not in comment  # file-level comment, no line


def test_build_review_summary():
    from quodeq.ci.review_builder import build_review_summary

    report = {
        "dimension": "security",
        "overallScore": "7.5/10",
        "overallGrade": "B",
        "totals": {
            "violationCount": 5,
            "severity": {"critical": 1, "major": 2, "minor": 2},
        },
    }
    summary = build_review_summary([report], duration_seconds=134)
    assert "7.5/10" in summary
    assert "1 critical" in summary.lower() or "1 Critical" in summary


def test_determine_verdict_critical():
    from quodeq.ci.review_builder import determine_verdict

    violations = [{"severity": "critical"}]
    assert determine_verdict(violations) == "REQUEST_CHANGES"


def test_determine_verdict_no_violations():
    from quodeq.ci.review_builder import determine_verdict

    assert determine_verdict([]) == "APPROVE"


def test_determine_verdict_minor_only():
    from quodeq.ci.review_builder import determine_verdict

    violations = [{"severity": "minor"}, {"severity": "low"}]
    assert determine_verdict(violations) == "COMMENT"
