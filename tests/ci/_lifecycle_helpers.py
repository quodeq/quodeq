"""Shared helpers for tests/ci/test_cli_lifecycle_integration_*.py siblings.

Split out of test_cli_lifecycle_integration.py.
"""
from __future__ import annotations

import json
from pathlib import Path


def _assert_partial_state_invariants(run_dir: Path, evidence_root: Path) -> None:
    """Assert both partial-state signals for a deadline-truncated run agree.

    Regression pin for c88be50e: a flexibility run with --max-duration
    truncated at ~850 of 3037 files but the dashboard rendered it as
    "complete" (6.6/Adequate). This asserts the two signals a caller must
    have already produced before invoking this helper:

      (a) status.json in ``run_dir`` shows state=done, exit_reason='deadline'
      (b) ``_compute_files_read`` reports files_read < source_file_count for
          a scenario mirroring c88be50e in miniature: 5 input files, 1
          pre-existing cache hit (carried through classify), 2 ok
          completions, 1 error, and 1 file with no marker at all (deadline
          hit mid-worker).

    The two are written by different code paths; the regression is that
    both are present, not that either is present in isolation.
    """
    from quodeq.analysis.cache.dimension_helpers import ClassifyResult
    from quodeq.analysis.cache.dimension_runner import _compute_files_read
    from quodeq.data.fs.run_status_store import read_status

    status = read_status(run_dir)
    assert status is not None
    assert status["state"] == "done"
    assert status["exit_reason"] == "deadline", (
        "deadline-truncated run must tag exit_reason='deadline' so the "
        "dashboard can render a Partial badge instead of green-lighting "
        "an incomplete run as complete"
    )

    all_files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
    classify = ClassifyResult(
        cached_findings=[{"file": "a.py", "p": "P1", "line": 1, "t": "violation", "w": "x"}],
        misses=["b.py", "c.py", "d.py", "e.py"],
        miss_keys={f: f"key-{f}" for f in ["b.py", "c.py", "d.py", "e.py"]},
    )

    jsonl = evidence_root / "flex_evidence.jsonl"
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    with jsonl.open("w") as out:
        # cached finding lands in the JSONL too (V2 runner mirrors hits in)
        out.write(json.dumps({"file": "a.py", "p": "P1", "line": 1, "t": "violation", "w": "x"}) + "\n")
        # b.py: one finding + ok marker
        out.write(json.dumps({"file": "b.py", "p": "P1", "line": 10, "t": "violation", "w": "y"}) + "\n")
        out.write(json.dumps({"_marker": "file_done", "file": "b.py", "status": "ok"}) + "\n")
        # c.py: no findings but ok marker (clean file)
        out.write(json.dumps({"_marker": "file_done", "file": "c.py", "status": "ok"}) + "\n")
        # d.py: error marker — must NOT count toward files_read
        out.write(json.dumps({"_marker": "file_done", "file": "d.py", "status": "error"}) + "\n")
        # e.py: no marker at all (deadline hit mid-worker) — must NOT count

    files_read = _compute_files_read(classify, jsonl, all_files)
    source_file_count = len(all_files)

    assert files_read == 3, (
        f"expected files_read=3 (1 hit + 2 ok dispatches), got {files_read}; "
        "the c88be50e symptom was files_read=len(input)=5, making coverage "
        "look 100% on a run that only completed 60% of files"
    )
    assert files_read < source_file_count, (
        f"deadline-truncated run must report files_read ({files_read}) < "
        f"source_file_count ({source_file_count}) — otherwise the dashboard "
        "computes coverage_pct=100 and renders a partial run as complete"
    )
