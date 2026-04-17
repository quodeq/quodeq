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
    summary = build_review_summary([report], [], [], duration_seconds=134)
    assert "7.5/10" in summary


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


# --- New classification tests ---


def test_classify_violations_matches_by_snippet():
    from quodeq.ci.review_builder import classify_violations

    current = [
        {"file": "a.py", "line": 10, "snippet": "eval(user_input)", "severity": "critical"},
        {"file": "a.py", "line": 20, "snippet": "exec(data)", "severity": "high"},
    ]
    baseline = [
        {"file": "a.py", "line": 5, "snippet": "eval(user_input)", "severity": "critical"},
    ]
    new, existing = classify_violations(current, baseline)
    assert len(existing) == 1
    assert existing[0]["snippet"] == "eval(user_input)"
    assert len(new) == 1
    assert new[0]["snippet"] == "exec(data)"


def test_classify_violations_normalizes_whitespace():
    from quodeq.ci.review_builder import classify_violations

    # Leading/trailing and internal repeated whitespace should collapse to same string
    current = [{"file": "a.py", "snippet": "  eval(   user_input   )  "}]
    baseline = [{"file": "a.py", "snippet": "eval(   user_input   )"}]
    new, existing = classify_violations(current, baseline)
    assert len(existing) == 1
    assert len(new) == 0


def test_classify_violations_different_files_are_different():
    from quodeq.ci.review_builder import classify_violations

    current = [{"file": "a.py", "snippet": "eval(x)"}]
    baseline = [{"file": "b.py", "snippet": "eval(x)"}]
    new, existing = classify_violations(current, baseline)
    assert len(new) == 1
    assert len(existing) == 0


def test_classify_violations_empty_baseline():
    from quodeq.ci.review_builder import classify_violations

    current = [{"file": "a.py", "snippet": "eval(x)"}]
    new, existing = classify_violations(current, [])
    assert len(new) == 1
    assert len(existing) == 0


def test_violation_to_comment_shows_new_prefix():
    from quodeq.ci.review_builder import violation_to_comment

    v = {"file": "a.py", "line": 10, "title": "SQL injection", "severity": "critical", "snippet": "x"}
    comment = violation_to_comment(v, status="new")
    assert "NEW" in comment["body"]


def test_violation_to_comment_shows_existing_prefix():
    from quodeq.ci.review_builder import violation_to_comment

    v = {"file": "a.py", "line": 10, "title": "SQL injection", "severity": "critical", "snippet": "x"}
    comment = violation_to_comment(v, status="existing")
    assert "Pre-existing" in comment["body"]


def test_determine_verdict_ignores_existing_critical():
    from quodeq.ci.review_builder import determine_verdict

    # Only new violations are passed in (existing ones are excluded upstream)
    new_violations = [{"severity": "minor"}]
    assert determine_verdict(new_violations) == "COMMENT"


def test_build_review_summary_shows_new_and_existing_counts():
    from quodeq.ci.review_builder import build_review_summary

    reports = [{"dimension": "security", "overallScore": "7.5/10", "overallGrade": "B"}]
    new = [{"severity": "critical"}, {"severity": "minor"}]
    existing = [{"severity": "minor"}]
    summary = build_review_summary(reports, new, existing, duration_seconds=60)
    assert "2 new" in summary.lower() or "2 New" in summary or "**2 new**" in summary
    assert "1 pre-existing" in summary.lower() or "1 Pre-existing" in summary or "**1 pre-existing**" in summary


def test_build_review_summary_shows_no_baseline_note_when_unavailable():
    from quodeq.ci.review_builder import build_review_summary

    reports = [{"dimension": "security", "overallScore": "8/10", "overallGrade": "A"}]
    summary = build_review_summary(reports, [], [], baseline_available=False)
    summary_lower = summary.lower()
    assert "no baseline" in summary_lower or "baseline not available" in summary_lower


def test_build_review_summary_no_baseline_note_when_available():
    from quodeq.ci.review_builder import build_review_summary

    reports = [{"dimension": "security", "overallScore": "8/10", "overallGrade": "A"}]
    summary = build_review_summary(reports, [], [], baseline_available=True)
    assert "no baseline" not in summary.lower()


def test_build_review_summary_includes_artifact_link():
    from quodeq.ci.review_builder import build_review_summary

    reports = [{"dimension": "security", "overallScore": "8/10", "overallGrade": "A"}]
    url = "https://example.com/run/123"
    summary = build_review_summary(reports, [], [], artifact_url=url)
    assert url in summary
    assert "Download full report" in summary


def test_build_review_summary_no_artifact_link_when_not_provided():
    from quodeq.ci.review_builder import build_review_summary

    reports = [{"dimension": "security", "overallScore": "8/10", "overallGrade": "A"}]
    summary = build_review_summary(reports, [], [])
    assert "Download full report" not in summary
