"""ci report --from-evidence reads evidence JSONL, not scored reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from quodeq.ci.cli import _handle_report


def _args(eval_dir: Path, from_evidence: bool) -> argparse.Namespace:
    return argparse.Namespace(
        ci_action="report",
        evaluation_dir=str(eval_dir),
        owner="o", repo="r", pr=1,
        token="t", duration=None, baseline_dir=None,
        artifact_url=None, from_evidence=from_evidence,
    )


def test_from_evidence_reads_evidence_not_scored(tmp_path: Path) -> None:
    eval_dir = tmp_path / "run"
    evidence_dir = eval_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "security_evidence.jsonl").write_text(
        json.dumps({
            "p": "SEC", "t": "violation", "d": "security",
            "file": "x.py", "line": 3, "severity": "high",
            "w": "Hardcoded password",
        }) + "\n"
    )

    with patch("quodeq.ci.reporter.fetch_pr_changed_lines", return_value={"x.py": {3}}), \
         patch("quodeq.ci.reporter.post_review") as posted:
        exit_code = _handle_report(_args(eval_dir, from_evidence=True))

    assert exit_code == 0
    assert posted.call_count == 1
    payload = posted.call_args.kwargs["payload"]
    assert len(payload["comments"]) == 1
    assert payload["comments"][0]["path"] == "x.py"


def test_from_evidence_no_findings_posts_approving_review(tmp_path: Path) -> None:
    """Empty evidence -> passing-summary COMMENT with no inline comments.

    In CI, "no findings" is the success case — PR authors must see that
    Quodeq ran and passed, not an absence of output indistinguishable from
    a broken job. GitHub Actions' default token is not permitted to submit
    APPROVE reviews (HTTP 422), so clean runs post a COMMENT review; the
    absence of inline comments + the summary body convey the pass.
    """
    eval_dir = tmp_path / "run"
    eval_dir.mkdir()
    # No evidence/ subdir means load_violations_from_evidence returns [].
    with patch("quodeq.ci.reporter.fetch_pr_changed_lines", return_value={}), \
         patch("quodeq.ci.reporter.post_review") as posted:
        exit_code = _handle_report(_args(eval_dir, from_evidence=True))
    assert exit_code == 0
    assert posted.call_count == 1
    payload = posted.call_args.kwargs["payload"]
    assert payload["event"] == "COMMENT"
    assert payload["comments"] == []


def test_from_evidence_ignores_baseline_dir(tmp_path: Path) -> None:
    """In evidence mode, --baseline-dir is ignored entirely.

    Locks in the contract: PR diff mode is baseline-free. Even if a caller
    mistakenly passes --baseline-dir, we must not load it.
    """
    eval_dir = tmp_path / "run"
    evidence_dir = eval_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "security_evidence.jsonl").write_text(
        json.dumps({
            "p": "SEC", "t": "violation", "d": "security",
            "file": "x.py", "line": 3, "severity": "high",
            "w": "X",
        }) + "\n"
    )
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()

    args = _args(eval_dir, from_evidence=True)
    args.baseline_dir = str(baseline_dir)

    with patch("quodeq.ci.reporter.fetch_pr_changed_lines", return_value={"x.py": {3}}), \
         patch("quodeq.ci.reporter.post_review"), \
         patch("quodeq.ci.reporter.load_evaluation_reports") as loader:
        exit_code = _handle_report(args)

    assert exit_code == 0
    # Evidence mode must not load scored reports, even for a provided baseline.
    loader.assert_not_called()


def test_from_evidence_excludes_dismissed_finding(tmp_path: Path) -> None:
    """A finding dismissed in the dashboard must not reach the posted review.

    In --from-evidence mode `evaluation_dir` (here `eval_dir`) IS the run
    directory, so the project dir (where actions.jsonl lives) is its
    *direct* parent -- one level shallower than the scored-report path.
    """
    from quodeq.services.dismissed import dismiss_finding

    eval_dir = tmp_path / "run"
    evidence_dir = eval_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "security_evidence.jsonl").write_text(
        "\n".join(json.dumps(o) for o in [
            {"p": "SEC-1", "req": "R-1", "t": "violation", "d": "security",
             "file": "x.py", "line": 3, "severity": "high", "w": "Dismissed one"},
            {"p": "SEC-2", "req": "R-2", "t": "violation", "d": "security",
             "file": "y.py", "line": 5, "severity": "high", "w": "Kept one"},
        ]) + "\n"
    )
    # project_dir is tmp_path (eval_dir's parent), matching evaluation_dir.parent.
    dismiss_finding(tmp_path, {"req": "R-1", "file": "x.py", "line": 3})

    with patch("quodeq.ci.reporter.fetch_pr_changed_lines", return_value={"x.py": {3}, "y.py": {5}}), \
         patch("quodeq.ci.reporter.post_review") as posted:
        exit_code = _handle_report(_args(eval_dir, from_evidence=True))

    assert exit_code == 0
    payload = posted.call_args.kwargs["payload"]
    paths = {c["path"] for c in payload["comments"]}
    assert paths == {"y.py"}


def test_from_evidence_excludes_deleted_finding(tmp_path: Path) -> None:
    """A (dimension, principle, file) permanently deleted in the dashboard
    must not reach the posted review, even though the evidence violation
    dict has no report-level 'dimension' matching the deleted entry directly
    (the wrapper report's dimension is the synthetic "pr-diff", not the
    violation's real dimension)."""
    eval_dir = tmp_path / "run"
    evidence_dir = eval_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "security_evidence.jsonl").write_text(
        "\n".join(json.dumps(o) for o in [
            {"p": "SEC-1", "req": "R-1", "t": "violation", "d": "security",
             "file": "x.py", "line": 3, "severity": "high", "w": "Deleted one"},
            {"p": "SEC-2", "req": "R-2", "t": "violation", "d": "security",
             "file": "y.py", "line": 5, "severity": "high", "w": "Kept one"},
        ]) + "\n"
    )
    (tmp_path / "deleted.json").write_text(json.dumps([
        {"dimension": "security", "principle": "SEC-1", "file": "x.py",
         "deleted_at": "2026-07-24T10:00:00Z"},
    ]))

    with patch("quodeq.ci.reporter.fetch_pr_changed_lines", return_value={"x.py": {3}, "y.py": {5}}), \
         patch("quodeq.ci.reporter.post_review") as posted:
        exit_code = _handle_report(_args(eval_dir, from_evidence=True))

    assert exit_code == 0
    payload = posted.call_args.kwargs["payload"]
    paths = {c["path"] for c in payload["comments"]}
    assert paths == {"y.py"}
