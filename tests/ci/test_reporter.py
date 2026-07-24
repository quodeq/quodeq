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


def test_load_evaluation_reports_resolves_project_dir_for_suppression(tmp_path):
    """Pins the `.parent.parent` project-dir derivation that feeds
    `filter_suppressed_violations`.

    Builds the real `<reports_root>/<project>/<run>/evaluation/` layout and
    dismisses one of two violations via the real `dismiss_finding()` event
    log (writing `<reports_root>/<project>/actions.jsonl`). If the
    project-dir math in `load_evaluation_reports` ever stops resolving to
    `<reports_root>/<project>`, `dismissed_keys()` reads an empty/wrong
    directory and both violations silently reappear.
    """
    from quodeq.ci.reporter import load_evaluation_reports
    from quodeq.services.dismissed import dismiss_finding

    reports_root = tmp_path / "reports"
    project = "proj"
    run = "20260101T000000"
    project_dir = reports_root / project
    eval_dir = project_dir / run / "evaluation"
    eval_dir.mkdir(parents=True)

    report = {
        "dimension": "security",
        "overallScore": "6.0/10",
        "overallGrade": "C",
        "violations": [
            {"req": "R-1", "file": "a.py", "line": 10, "title": "SQLi", "reason": "bad input", "severity": "critical"},
            {"req": "R-2", "file": "b.py", "line": 20, "title": "XSS", "reason": "unescaped output", "severity": "major"},
        ],
        "totals": {"violationCount": 2, "severity": {"critical": 1, "major": 1, "minor": 0}},
    }
    (eval_dir / "security.json").write_text(json.dumps(report), encoding="utf-8")

    # Real dismiss path (ActionLogWriter under the hood) rather than hand-
    # rolling actions.jsonl: a hand-rolled event_id must be a valid UUID or
    # read_action_events silently skips the line as malformed.
    dismiss_finding(project_dir, {"req": "R-1", "file": "a.py", "line": 10})

    reports = load_evaluation_reports(eval_dir)
    assert len(reports) == 1
    assert [v["req"] for v in reports[0]["violations"]] == ["R-2"]


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


def test_build_review_payload_passes_through_artifact_url():
    from quodeq.ci.reporter import build_review_payload

    reports = [{
        "dimension": "security",
        "overallScore": "9/10",
        "overallGrade": "A",
        "violations": [],
        "totals": {"violationCount": 0, "severity": {}},
    }]
    url = "https://x"
    payload = build_review_payload(reports, artifact_url=url)
    assert url in payload["body"]


def test_build_review_payload_passes_through_baseline_available_false():
    from quodeq.ci.reporter import build_review_payload

    reports = [{
        "dimension": "security",
        "overallScore": "9/10",
        "overallGrade": "A",
        "violations": [],
        "totals": {"violationCount": 0, "severity": {}},
    }]
    payload = build_review_payload(reports, baseline_available=False)
    assert "no baseline" in payload["body"].lower()


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
