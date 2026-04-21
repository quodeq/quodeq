"""Tests for PR-diff-aware filtering of review comments.

Root cause of prior `Quodeq Review` 422 failures: review comments referenced
paths/lines outside the PR's actual diff, which GitHub rejects with
"Path could not be resolved" / "Line could not be resolved".

These tests cover the fix: fetch the PR's changed lines, parse the patch
hunks, filter comments to in-diff scope before posting.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.ci.reporter import (
    _parse_hunks,
    build_review_payload,
    fetch_pr_changed_lines,
    filter_comments_to_diff,
)


# ---------------------------------------------------------------------------
# _parse_hunks — extract RIGHT-side line numbers from a unified diff patch
# ---------------------------------------------------------------------------

def test_parse_hunks_empty_patch() -> None:
    assert _parse_hunks("") == set()
    assert _parse_hunks(None) == set()


def test_parse_hunks_simple_hunk_with_additions_and_context() -> None:
    """A hunk starting at new_start=10 with 2 context + 1 addition + 1 context
    covers lines 10, 11, 12, 13 on the RIGHT side."""
    patch_text = (
        "@@ -10,3 +10,4 @@\n"
        " context line at 10\n"
        " context line at 11\n"
        "+added line at 12\n"
        " context line at 13\n"
    )
    assert _parse_hunks(patch_text) == {10, 11, 12, 13}


def test_parse_hunks_skips_removed_lines() -> None:
    """Removed lines (starting with '-') are LEFT-only; they don't advance
    the RIGHT-side counter and are not included in the set."""
    patch_text = (
        "@@ -20,3 +20,2 @@\n"
        " context line at 20\n"
        "-removed line (was line 21 on LEFT; not on RIGHT)\n"
        " context line at 21\n"
    )
    assert _parse_hunks(patch_text) == {20, 21}


def test_parse_hunks_multiple_hunks_union() -> None:
    patch_text = (
        "@@ -1,1 +1,2 @@\n"
        " a\n"
        "+b\n"
        "@@ -50,1 +51,1 @@\n"
        "+new line at 51\n"
    )
    assert _parse_hunks(patch_text) == {1, 2, 51}


def test_parse_hunks_ignores_no_newline_marker() -> None:
    """The `\\ No newline at end of file` marker must not advance the counter."""
    patch_text = (
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
        "\\ No newline at end of file\n"
    )
    assert _parse_hunks(patch_text) == {1}


# ---------------------------------------------------------------------------
# fetch_pr_changed_lines — call GitHub /pulls/<n>/files and build the map
# ---------------------------------------------------------------------------

def test_fetch_pr_changed_lines_single_page() -> None:
    files_response = [
        {
            "filename": "src/a.py",
            "patch": "@@ -5,0 +5,2 @@\n+line 5 added\n+line 6 added\n",
        },
        {
            "filename": "src/b.py",
            "patch": "@@ -100,1 +100,1 @@\n-old\n+replacement at 100\n",
        },
    ]
    with patch("quodeq.ci.reporter._github_get") as mock_get:
        mock_get.return_value = files_response
        result = fetch_pr_changed_lines("quodeq", "quodeq", 42, "ghp_test")
    assert result == {"src/a.py": {5, 6}, "src/b.py": {100}}
    mock_get.assert_called_once()


def test_fetch_pr_changed_lines_paginates() -> None:
    page1 = [{"filename": f"f{i}.py", "patch": f"@@ -1,1 +1,1 @@\n+x\n"} for i in range(100)]
    page2 = [{"filename": "last.py", "patch": "@@ -1,1 +1,1 @@\n+last\n"}]
    with patch("quodeq.ci.reporter._github_get") as mock_get:
        mock_get.side_effect = [page1, page2]
        result = fetch_pr_changed_lines("o", "r", 1, "tok")
    assert len(result) == 101
    assert "last.py" in result
    assert mock_get.call_count == 2


def test_fetch_pr_changed_lines_skips_files_without_patch() -> None:
    """Binary files (no `patch` in response) are skipped entirely."""
    files_response = [
        {"filename": "image.png"},  # binary, no patch key
        {"filename": "text.py", "patch": "@@ -1,0 +1,1 @@\n+hi\n"},
    ]
    with patch("quodeq.ci.reporter._github_get") as mock_get:
        mock_get.return_value = files_response
        result = fetch_pr_changed_lines("o", "r", 1, "t")
    assert result == {"text.py": {1}}


# ---------------------------------------------------------------------------
# filter_comments_to_diff — drop comments outside the PR's changed lines
# ---------------------------------------------------------------------------

def test_filter_comments_to_diff_keeps_in_diff() -> None:
    comments = [
        {"path": "src/a.py", "line": 10, "body": "issue in diff"},
    ]
    changed = {"src/a.py": {10, 11, 12}}
    kept, dropped = filter_comments_to_diff(comments, changed)
    assert kept == comments
    assert dropped == 0


def test_filter_comments_to_diff_drops_out_of_diff_path() -> None:
    comments = [
        {"path": "src/a.py", "line": 10, "body": "in diff"},
        {"path": "src/z.py", "line": 10, "body": "NOT in diff"},
    ]
    changed = {"src/a.py": {10}}
    kept, dropped = filter_comments_to_diff(comments, changed)
    assert len(kept) == 1
    assert kept[0]["path"] == "src/a.py"
    assert dropped == 1


def test_filter_comments_to_diff_drops_out_of_diff_line() -> None:
    comments = [
        {"path": "src/a.py", "line": 10, "body": "in diff"},
        {"path": "src/a.py", "line": 999, "body": "in file but wrong line"},
    ]
    changed = {"src/a.py": {10}}
    kept, dropped = filter_comments_to_diff(comments, changed)
    assert len(kept) == 1
    assert kept[0]["line"] == 10
    assert dropped == 1


def test_filter_comments_to_diff_drops_comments_with_no_line() -> None:
    """Comments missing a `line` key can't be anchored to a diff position."""
    comments = [
        {"path": "src/a.py", "body": "no line info"},
    ]
    changed = {"src/a.py": {1, 2, 3}}
    kept, dropped = filter_comments_to_diff(comments, changed)
    assert kept == []
    assert dropped == 1


# ---------------------------------------------------------------------------
# build_review_payload — integrates the filter when changed_lines is provided
# ---------------------------------------------------------------------------

def test_build_review_payload_filters_when_changed_lines_provided() -> None:
    reports = [{
        "dimension": "security",
        "overallScore": "7/10",
        "overallGrade": "B",
        "violations": [
            {"file": "src/a.py", "line": 10, "title": "in diff", "reason": "", "severity": "minor"},
            {"file": "src/z.py", "line": 99, "title": "out of diff", "reason": "", "severity": "minor"},
        ],
        "totals": {"violationCount": 2, "severity": {"minor": 2}},
    }]
    payload = build_review_payload(reports, changed_lines={"src/a.py": {10}})
    assert len(payload["comments"]) == 1
    assert payload["comments"][0]["path"] == "src/a.py"


def test_build_review_payload_summary_mentions_out_of_diff_count() -> None:
    reports = [{
        "dimension": "security",
        "overallScore": "7/10",
        "overallGrade": "B",
        "violations": [
            {"file": "src/z.py", "line": 99, "title": "out of diff", "reason": "", "severity": "major"},
        ],
        "totals": {"violationCount": 1, "severity": {"major": 1}},
    }]
    payload = build_review_payload(reports, changed_lines={})  # empty diff → all dropped
    assert payload["comments"] == []
    # Summary body should mention the dropped count so users aren't misled.
    assert "outside the pr diff" in payload["body"].lower()


def test_build_review_payload_no_filter_when_changed_lines_is_none() -> None:
    """Backward compat: when changed_lines is not passed, all comments included."""
    reports = [{
        "dimension": "security",
        "overallScore": "7/10",
        "overallGrade": "B",
        "violations": [
            {"file": "src/a.py", "line": 10, "title": "x", "reason": "", "severity": "minor"},
        ],
        "totals": {"violationCount": 1, "severity": {"minor": 1}},
    }]
    payload = build_review_payload(reports)
    assert len(payload["comments"]) == 1


# ---------------------------------------------------------------------------
# CLI fallback — fetch failure must still produce a summary-only review
# ---------------------------------------------------------------------------

def test_cli_handle_report_falls_back_on_fetch_failure(tmp_path, capsys) -> None:
    """When fetch_pr_changed_lines raises, post a summary-only review (no crash)."""
    import json
    from unittest.mock import MagicMock, patch

    from quodeq.ci.cli import _handle_report

    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "security.json").write_text(json.dumps({
        "dimension": "security",
        "overallScore": "7/10",
        "overallGrade": "B",
        "violations": [
            {"file": "a.py", "line": 5, "title": "T", "reason": "R", "severity": "major"},
        ],
        "totals": {"violationCount": 1, "severity": {"major": 1}},
    }))

    args = MagicMock()
    args.evaluation_dir = str(eval_dir)
    args.baseline_dir = None
    args.owner = "o"
    args.repo = "r"
    args.pr = 1
    args.token = "fake"
    args.duration = 5
    args.artifact_url = None

    captured = {}

    def fake_post(**kwargs):
        captured.update(kwargs["payload"])
        return {"id": 99}

    with patch(
        "quodeq.ci.reporter.fetch_pr_changed_lines",
        side_effect=RuntimeError("simulated fetch failure"),
    ), patch("quodeq.ci.reporter.post_review", side_effect=fake_post):
        exit_code = _handle_report(args)

    assert exit_code == 0, "fetch failure must NOT abort the report command"
    # Fallback behavior: comments dropped, summary still posted.
    assert captured["comments"] == []
    assert "## Quodeq Evaluation" in captured["body"]
    # Stderr mentions the fallback so operators see the warning.
    assert "could not fetch PR diff" in capsys.readouterr().err
