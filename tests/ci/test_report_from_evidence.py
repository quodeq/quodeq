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
    """Empty evidence -> approving review with no comments (not silence).

    In CI, "no findings" is the success case — PR authors must see that
    Quodeq ran and passed, not an absence of output indistinguishable from
    a broken job.
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
    assert payload["event"] == "APPROVE"
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
