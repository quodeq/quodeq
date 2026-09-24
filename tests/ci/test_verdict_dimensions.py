"""Performance findings are review comments only; they never request changes."""
from quodeq.ci.reporter import build_review_payload
from quodeq.ci.review_builder import determine_verdict


def test_performance_critical_does_not_request_changes():
    assert determine_verdict([{"severity": "critical", "dimension": "performance"}]) == "COMMENT"


def test_security_critical_still_requests_changes():
    assert determine_verdict([{"severity": "critical", "dimension": "security"}]) == "REQUEST_CHANGES"


def test_critical_without_a_dimension_still_requests_changes():
    # Scored-mode report violations do not always carry a dimension key.
    assert determine_verdict([{"severity": "critical"}]) == "REQUEST_CHANGES"


def test_security_critical_blocks_next_to_performance_noise():
    violations = [
        {"severity": "critical", "dimension": "performance"},
        {"severity": "critical", "dimension": "security"},
    ]
    assert determine_verdict(violations) == "REQUEST_CHANGES"


def test_evidence_mode_performance_critical_posts_a_comment_review():
    report = {"dimension": "performance", "violations": [{
        "file": "src/a.py", "line": 3, "severity": "critical", "title": "t",
        "reason": "r", "snippet": "s", "dimension": "performance",
    }]}
    payload = build_review_payload([report], changed_lines={"src/a.py": {3}})
    assert payload["event"] == "COMMENT"
    assert len(payload["comments"]) == 1
