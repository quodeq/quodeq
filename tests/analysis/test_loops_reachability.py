"""Tests for the post-run model-reachability guard.

Motivating incident: the CI Ollama model name in quodeq.env pointed at a model
that no longer existed on the runner. Every analysis call returned HTTP 404, so
``_call_api`` flagged each call lossy and ``run_api_analysis`` wrote no markers.
The failure-streak breaker (which only counts ``file_done`` error markers) never
saw the failures, ``check_zero_findings`` is bypassed in diff/incremental mode,
and the run exited 0 — green CI that did zero work for weeks.

The guard pinned down here raises ``EvaluationError`` (mapped to exit 1 by the
CLI) when files were dispatched to the model but *none* were successfully
analysed: every file ended on an ``error`` marker and not one on ``ok``. That is
the signature of an unreachable/misconfigured model. A legitimately empty diff
scan (no applicable files dispatched -> no markers at all) does NOT raise.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.analysis._loops import check_model_reachable
from quodeq.analysis.errors import EvaluationError


def _write_evidence(run_dir: Path, dim: str, markers: list[tuple[str, str]]) -> None:
    """Write a ``<dim>_evidence.jsonl`` with the given (file, status) markers."""
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / f"{dim}_evidence.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for file, status in markers:
            fh.write(json.dumps({
                "_marker": "file_done", "file": file, "status": status,
            }) + "\n")


def test_all_error_markers_raises(tmp_path):
    """Files dispatched, every one failed (0 ok) -> model unreachable -> raise."""
    _write_evidence(tmp_path, "security", [("a.py", "error"), ("b.py", "error")])
    with pytest.raises(EvaluationError) as exc:
        check_model_reachable(tmp_path)
    # Message should point at the model / provider so the cause is obvious.
    assert "2" in str(exc.value)
    assert "model" in str(exc.value).lower()


def test_all_error_across_multiple_dims_raises(tmp_path):
    _write_evidence(tmp_path, "security", [("a.py", "error")])
    _write_evidence(tmp_path, "reliability", [("b.py", "error"), ("c.py", "error")])
    with pytest.raises(EvaluationError):
        check_model_reachable(tmp_path)


def test_any_ok_marker_does_not_raise(tmp_path):
    """At least one successful analysis means the model is reachable; a partial
    failure is handled by the existing graceful-cancellation path, not here."""
    _write_evidence(tmp_path, "security", [("a.py", "ok"), ("b.py", "error")])
    check_model_reachable(tmp_path)  # must not raise


def test_only_ok_markers_does_not_raise(tmp_path):
    _write_evidence(tmp_path, "security", [("a.py", "ok"), ("b.py", "ok")])
    check_model_reachable(tmp_path)


def test_latest_marker_per_file_wins(tmp_path):
    """A file that errored then later succeeded (re-dispatch) counts as ok."""
    _write_evidence(tmp_path, "security", [("a.py", "error"), ("a.py", "ok")])
    check_model_reachable(tmp_path)  # latest is ok -> reachable -> no raise


def test_no_markers_does_not_raise(tmp_path):
    """Legitimately empty scan: a diff that touches none of the dimension's
    language dispatches nothing, so there are no markers at all. Not a failure."""
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "security_evidence.jsonl").write_text("", encoding="utf-8")
    check_model_reachable(tmp_path)


def test_no_evidence_dir_does_not_raise(tmp_path):
    check_model_reachable(tmp_path)  # nothing written yet


def test_run_dir_none_does_not_raise():
    check_model_reachable(None)
