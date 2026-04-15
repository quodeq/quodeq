import json
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_load_evaluation_reports(tmp_path):
    from quodeq.ci.reporter import load_evaluation_reports

    eval_dir = tmp_path / "evaluation"
    eval_dir.mkdir()
    report = {
        "dimension": "security",
        "overallScore": "7.5/10",
        "overallGrade": "B",
        "violations": [
            {"file": "a.py", "line": 10, "title": "Issue", "reason": "Bad", "severity": "critical"},
        ],
        "totals": {"violationCount": 1, "severity": {"critical": 1, "major": 0, "minor": 0}},
    }
    (eval_dir / "security.json").write_text(json.dumps(report))
    # _full.json files should be skipped
    (eval_dir / "security_full.json").write_text(json.dumps(report))

    reports = load_evaluation_reports(eval_dir)
    assert len(reports) == 1
    assert reports[0]["dimension"] == "security"


def test_build_review_payload():
    from quodeq.ci.reporter import build_review_payload

    reports = [{
        "dimension": "security",
        "overallScore": "7.5/10",
        "overallGrade": "B",
        "violations": [
            {"file": "a.py", "line": 10, "title": "SQL injection", "reason": "Bad input", "severity": "critical"},
        ],
        "totals": {"violationCount": 1, "severity": {"critical": 1, "major": 0, "minor": 0}},
    }]
    payload = build_review_payload(reports)
    assert payload["event"] == "REQUEST_CHANGES"
    assert len(payload["comments"]) == 1
    assert payload["comments"][0]["path"] == "a.py"
    assert "body" in payload  # review summary


def test_post_review_calls_github_api():
    from quodeq.ci.reporter import post_review

    payload = {
        "body": "summary",
        "event": "COMMENT",
        "comments": [],
    }
    with patch("quodeq.ci.reporter._github_request") as mock_req:
        mock_req.return_value = {"id": 123}
        result = post_review(
            owner="quodeq",
            repo="quodeq",
            pr_number=42,
            payload=payload,
            token="ghp_test",
        )
        mock_req.assert_called_once()
        assert result["id"] == 123
