"""Shared helpers for tests/ci/test_cli_lifecycle_integration_*.py siblings.

Split out of test_cli_lifecycle_integration.py.
"""
from __future__ import annotations

import json
from pathlib import Path


def _assert_deadline_status(run_dir: Path) -> None:
    """Signal (a): status.json tags the run done with exit_reason='deadline'."""
    from quodeq.data.fs.run_status_store import read_status

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status["exit_reason"] == "deadline", (
        "deadline-truncated run must tag exit_reason='deadline' so the "
        "dashboard can render a Partial badge instead of green-lighting "
        "an incomplete run as complete"
    )


def _write_truncated_dim_jsonl(jsonl: Path) -> None:
    """A dim's evidence JSONL for the c88be50e scenario, in miniature.

    Five input files: one pre-existing cache hit mirrored in by the V2
    runner, two ok completions, one error, and one with no marker at all
    because the deadline landed mid-worker.
    """
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("w") as out:
        out.write(json.dumps({"file": "a.py", "p": "P1", "line": 1, "t": "violation", "w": "x"}) + "\n")
        out.write(json.dumps({"file": "b.py", "p": "P1", "line": 10, "t": "violation", "w": "y"}) + "\n")
        out.write(json.dumps({"_marker": "file_done", "file": "b.py", "status": "ok"}) + "\n")
        out.write(json.dumps({"_marker": "file_done", "file": "c.py", "status": "ok"}) + "\n")
        out.write(json.dumps({"_marker": "file_done", "file": "d.py", "status": "error"}) + "\n")


def _assert_partial_coverage(evidence_root: Path) -> None:
    """Signal (b): _compute_files_read reports fewer files read than input."""
    from quodeq.analysis.cache.dimension_helpers import ClassifyResult
    from quodeq.analysis.cache.dimension_runner import _compute_files_read

    all_files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
    misses = ["b.py", "c.py", "d.py", "e.py"]
    classify = ClassifyResult(
        cached_findings=[{"file": "a.py", "p": "P1", "line": 1, "t": "violation", "w": "x"}],
        misses=misses,
        miss_keys={f: f"key-{f}" for f in misses},
    )
    jsonl = evidence_root / "flex_evidence.jsonl"
    _write_truncated_dim_jsonl(jsonl)

    files_read = _compute_files_read(classify, jsonl, all_files)
    assert files_read == 3, (
        f"expected files_read=3 (1 hit + 2 ok dispatches), got {files_read}; "
        "the c88be50e symptom was files_read=len(input)=5, making coverage "
        "look 100% on a run that only completed 60% of files"
    )
    assert files_read < len(all_files), (
        f"deadline-truncated run must report files_read ({files_read}) < "
        f"source_file_count ({len(all_files)}) — otherwise the dashboard "
        "computes coverage_pct=100 and renders a partial run as complete"
    )


def _assert_partial_state_invariants(run_dir: Path, evidence_root: Path) -> None:
    """Assert both partial-state signals for a deadline-truncated run agree.

    Regression pin for c88be50e: a flexibility run with --max-duration
    truncated at ~850 of 3037 files but the dashboard rendered it as
    "complete" (6.6/Adequate). The two signals are written by different code
    paths; the regression is that both are present, not either in isolation.
    The caller must already have produced the run this checks.
    """
    _assert_deadline_status(run_dir)
    _assert_partial_coverage(evidence_root)
