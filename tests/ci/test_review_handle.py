"""Tests for quodeq review: handle_review flow and the run_diff_evaluation entry."""
from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

from quodeq.cli_evaluation import run_diff_evaluation
from quodeq.ci.review import handle_review
from quodeq.services.dismissed import dismiss_finding


def test_handle_review_default_does_not_pass_dimensions(tmp_path):
    """When no --dimensions flag is given, handle_review must pass
    dimensions=None so the evaluate entry defaults to all dimensions."""

    args = argparse.Namespace(
        pr=None,
        dimensions=None,
        pool_budget=None,
        output=str(tmp_path),
        dry_run=True,
    )

    pr_result = MagicMock()
    pr_result.stdout = json.dumps({"number": 7, "baseRefName": "main"})
    repo_result = MagicMock()
    repo_result.stdout = json.dumps({"owner": {"login": "org"}, "name": "repo"})

    with patch("quodeq.ci.review.subprocess.run", side_effect=[pr_result, repo_result]), \
         patch("quodeq.cli_evaluation.run_diff_evaluation", return_value=0) as mock_run:
        from quodeq.ci.review import handle_review
        handle_review(args)

    assert mock_run.call_args.kwargs["dimensions"] is None


def test_handle_review_expands_dimension_alias(tmp_path):
    """When --dimensions sec is given, handle_review expands it to 'security'."""

    args = argparse.Namespace(
        pr=None,
        dimensions="sec",
        pool_budget=None,
        output=str(tmp_path),
        dry_run=True,
    )

    pr_result = MagicMock()
    pr_result.stdout = json.dumps({"number": 7, "baseRefName": "main"})
    repo_result = MagicMock()
    repo_result.stdout = json.dumps({"owner": {"login": "org"}, "name": "repo"})

    with patch("quodeq.ci.review.subprocess.run", side_effect=[pr_result, repo_result]), \
         patch("quodeq.cli_evaluation.run_diff_evaluation", return_value=0) as mock_run:
        from quodeq.ci.review import handle_review
        handle_review(args)

    assert mock_run.call_args.kwargs["dimensions"] == "security"


def test_review_invokes_evaluate_with_diff_from_not_incremental(tmp_path, monkeypatch):
    """quodeq review must call evaluate --diff-from origin/<base>, not --incremental."""

    captured_calls: list[dict] = []

    def fake_run_diff_evaluation(src, **kwargs):
        captured_calls.append({"src": src, **kwargs})
        return 0

    monkeypatch.setattr("quodeq.ci.review.detect_pr", lambda pr_override=None: (42, "develop"))
    monkeypatch.setattr("quodeq.ci.review.get_repo_info", lambda: ("owner", "repo"))
    monkeypatch.setattr("quodeq.ci.review.get_github_token", lambda: "t")
    monkeypatch.setattr("quodeq.ci.review.snapshot_run_dirs", lambda d: set())
    # run_diff_evaluation is imported INSIDE handle_review; patch it at its
    # source module so the in-function import picks up the patch.
    monkeypatch.setattr("quodeq.cli_evaluation.run_diff_evaluation", fake_run_diff_evaluation)
    # short-circuit the post/report stage for this test. load_violations_from_evidence
    # is imported inside handle_review, so patch at its source.
    monkeypatch.setattr(
        "quodeq.ci._evidence_reader.load_violations_from_evidence",
        lambda d: [],
    )

    args = argparse.Namespace(
        pr=42, dimensions=None, pool_budget=None,
        output=str(tmp_path / "out"), dry_run=True,
    )

    handle_review(args)
    # handle_review may exit 1 if no new runs are found (expected — we mock
    # snapshot_run_dirs to return empty both before and after). We don't care
    # about the exit code for this test; we care about the evaluation call.
    assert captured_calls, "review did not run a diff evaluation"
    call = captured_calls[0]
    assert call["base_ref"] == "origin/develop"
    assert "incremental" not in call


def test_handle_review_excludes_dismissed_finding(tmp_path, monkeypatch, capsys):
    """A finding dismissed in the dashboard must not reach the diff-mode
    review `quodeq review` builds from evidence JSONL -- same suppression
    contract as `ci report --from-evidence` (both read raw evidence, no
    scored reports)."""

    output_dir = tmp_path / "out"
    project_dir = output_dir / "proj"
    run_dir = project_dir / "run1"
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "security_evidence.jsonl").write_text(
        "\n".join(json.dumps(o) for o in [
            {"p": "SEC-1", "req": "R-1", "t": "violation", "d": "security",
             "file": "x.py", "line": 3, "severity": "high", "w": "Dismissed one"},
            {"p": "SEC-2", "req": "R-2", "t": "violation", "d": "security",
             "file": "y.py", "line": 5, "severity": "high", "w": "Kept one"},
        ]) + "\n"
    )
    # evidence_dir.parent.parent == project_dir -- where actions.jsonl lives.
    dismiss_finding(project_dir, {"req": "R-1", "file": "x.py", "line": 3})

    monkeypatch.setattr("quodeq.ci.review.detect_pr", lambda pr_override=None: (42, "develop"))
    monkeypatch.setattr("quodeq.ci.review.get_repo_info", lambda: ("owner", "repo"))
    monkeypatch.setattr(
        "quodeq.cli_evaluation.run_diff_evaluation",
        lambda src, **kwargs: 0,
    )

    args = argparse.Namespace(
        pr=42, dimensions=None, pool_budget=None,
        output=str(output_dir), dry_run=True,
    )

    with patch("quodeq.ci.review.snapshot_run_dirs", side_effect=[set(), {run_dir}]):
        rc = handle_review(args)

    assert rc == 0
    out = capsys.readouterr().out
    assert "1 violation(s) found in diff" in out


def test_handle_review_time_limit_zero_means_unlimited(tmp_path):
    """--time-limit 0 is documented as unlimited; the `or 300` fallback must
    not swallow it (same falsy-drop bug as the dashboard's unlimited runs)."""

    args = argparse.Namespace(
        pr=None,
        dimensions=None,
        pool_budget=0,
        output=str(tmp_path),
        dry_run=True,
    )

    pr_result = MagicMock()
    pr_result.stdout = json.dumps({"number": 7, "baseRefName": "main"})
    repo_result = MagicMock()
    repo_result.stdout = json.dumps({"owner": {"login": "org"}, "name": "repo"})

    with patch("quodeq.ci.review.subprocess.run", side_effect=[pr_result, repo_result]), \
         patch("quodeq.cli_evaluation.run_diff_evaluation", return_value=0) as mock_run:
        from quodeq.ci.review import handle_review
        handle_review(args)

    assert mock_run.call_args.kwargs["time_limit"] == 0


def test_run_diff_evaluation_builds_evaluate_namespace(tmp_path):
    """The typed entry hands the REAL parser an evaluate argv; assert the
    resulting namespace fields (argv round-trip stays inside the CLI pkg)."""

    captured = {}

    def fake_run_evaluate(ns):
        captured["ns"] = ns
        return 0

    with patch("quodeq.cli_evaluation.run_evaluate", fake_run_evaluate):
        rc = run_diff_evaluation(
            ".", base_ref="origin/main", output_dir=tmp_path,
            dimensions="security", time_limit=120,
        )

    assert rc == 0
    ns = captured["ns"]
    assert ns.repo == "."
    assert ns.diff_from == "origin/main"
    assert ns.output == str(tmp_path)
    assert ns.dimensions == "security"
    assert ns.pool_budget == 120  # --time-limit shares the pool_budget dest


def test_run_diff_evaluation_defaults(tmp_path):

    captured = {}

    def fake_run_evaluate(ns):
        captured["ns"] = ns
        return 0

    with patch("quodeq.cli_evaluation.run_evaluate", fake_run_evaluate):
        run_diff_evaluation(".", base_ref="origin/develop", output_dir=tmp_path)

    ns = captured["ns"]
    assert ns.dimensions is None
    assert ns.pool_budget == 300
