"""Tests for the `quodeq ci` CLI subcommand."""
from __future__ import annotations


def test_ci_report_args_parsed():
    from quodeq.cli_parser import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "ci", "report",
        "--evaluation-dir", "/tmp/eval",
        "--owner", "quodeq",
        "--repo", "quodeq",
        "--pr", "42",
    ])
    assert args.evaluation_dir == "/tmp/eval"
    assert args.owner == "quodeq"
    assert args.repo == "quodeq"
    assert args.pr == 42


def test_ci_report_baseline_dir_parsed():
    from quodeq.cli_parser import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "ci", "report",
        "--evaluation-dir", "/tmp/eval",
        "--baseline-dir", "/tmp/baseline",
        "--owner", "quodeq",
        "--repo", "quodeq",
        "--pr", "42",
    ])
    assert args.baseline_dir == "/tmp/baseline"


def test_ci_report_baseline_dir_optional():
    from quodeq.cli_parser import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "ci", "report",
        "--evaluation-dir", "/tmp/eval",
        "--owner", "quodeq",
        "--repo", "quodeq",
        "--pr", "42",
    ])
    assert args.baseline_dir is None


def test_ci_report_artifact_url_parsed():
    from quodeq.cli_parser import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "ci", "report",
        "--evaluation-dir", "/tmp/eval",
        "--owner", "quodeq",
        "--repo", "quodeq",
        "--pr", "42",
        "--artifact-url", "https://example.com/run/123",
    ])
    assert args.artifact_url == "https://example.com/run/123"


def test_ci_report_artifact_url_optional():
    from quodeq.cli_parser import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "ci", "report",
        "--evaluation-dir", "/tmp/eval",
        "--owner", "quodeq",
        "--repo", "quodeq",
        "--pr", "42",
    ])
    assert args.artifact_url is None


def test_handle_report_loads_baseline(tmp_path):
    """Verify that _handle_report loads baseline violations when --baseline-dir is provided."""
    import json
    from unittest.mock import MagicMock, patch

    from quodeq.ci.cli import _handle_report

    # Create fake current report
    current_eval = tmp_path / "current"
    current_eval.mkdir()
    (current_eval / "security.json").write_text(json.dumps({
        "dimension": "security",
        "overallScore": "7.5/10",
        "overallGrade": "B",
        "violations": [
            {"file": "a.py", "snippet": "eval(x)", "severity": "critical", "title": "Eval", "reason": "Bad"},
            {"file": "a.py", "snippet": "exec(y)", "severity": "high", "title": "Exec", "reason": "Bad"},
        ],
        "totals": {"violationCount": 2, "severity": {"critical": 1, "major": 1, "minor": 0}},
    }))

    # Create fake baseline report with one matching violation
    baseline_eval = tmp_path / "baseline"
    baseline_eval.mkdir()
    (baseline_eval / "security.json").write_text(json.dumps({
        "dimension": "security",
        "overallScore": "7.5/10",
        "overallGrade": "B",
        "violations": [
            {"file": "a.py", "snippet": "eval(x)", "severity": "critical", "title": "Eval", "reason": "Bad"},
        ],
        "totals": {"violationCount": 1, "severity": {"critical": 1, "major": 0, "minor": 0}},
    }))

    args = MagicMock()
    args.evaluation_dir = str(current_eval)
    args.baseline_dir = str(baseline_eval)
    args.owner = "test"
    args.repo = "test"
    args.pr = 1
    args.token = "fake"
    args.duration = 10
    args.artifact_url = None

    captured_payload = {}

    def fake_post(**kwargs):
        captured_payload.update(kwargs["payload"])
        return {"id": 1}

    with patch("quodeq.ci.reporter.post_review", side_effect=fake_post):
        exit_code = _handle_report(args)

    assert exit_code == 0
    # eval(x) is in baseline → existing; exec(y) is NOT → new
    # new violation has severity "high" → verdict is REQUEST_CHANGES
    assert captured_payload["event"] == "REQUEST_CHANGES"
    bodies = [c["body"] for c in captured_payload["comments"]]
    new_comments = [b for b in bodies if "NEW" in b]
    existing_comments = [b for b in bodies if "Pre-existing" in b]
    assert len(new_comments) == 1
    assert len(existing_comments) == 1
