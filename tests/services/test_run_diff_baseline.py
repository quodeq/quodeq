"""The default baseline is chosen per dimension: a finished run that has the report.

A cancelled partial run, or a run that never evaluated the dimension, must not
become the silent baseline: findings in files it never read would all count
as new.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.services.run_diff import diff_runs

_PROJECT = "p"
_DIM = "maintainability"
_OTHER_DIM = "security"


def _run(root: Path, run_id: str, started_at: str, state: str, dims: dict[str, list[dict]]) -> None:
    run_dir = root / _PROJECT / run_id
    (run_dir / "evaluation").mkdir(parents=True)
    for dim, violations in dims.items():
        (run_dir / "evaluation" / f"{dim}.json").write_text(json.dumps({
            "dimension": dim, "principles": [], "violations": violations, "compliance": []}),
            encoding="utf-8")
    (run_dir / "status.json").write_text(json.dumps({"state": state, "started_at": started_at}),
                                          encoding="utf-8")


def _v(req: str) -> dict:
    return {"req": req, "file": "a.py", "line": 1, "snippet": f"{req} snippet", "severity": "minor"}


def test_default_baseline_prefers_a_finished_run_with_the_dimension(tmp_path: Path) -> None:
    _run(tmp_path, "r-done-old", "2026-09-10T00:00:00Z", "done", {_DIM: [_v("M-REU-1")]})
    _run(tmp_path, "r-other-dim", "2026-09-15T00:00:00Z", "done", {_OTHER_DIM: [_v("S-CON-1")]})
    _run(tmp_path, "r-cancelled", "2026-09-20T00:00:00Z", "cancelled", {_DIM: []})
    _run(tmp_path, "r-curr", "2026-09-26T00:00:00Z", "done", {_DIM: [_v("M-REU-1")]})

    out = diff_runs(tmp_path, _PROJECT, "r-curr", None)

    dim = out["dimensions"][_DIM]
    assert dim["againstRunId"] == "r-done-old"
    assert dim["counts"]["same"] == 1 and dim["counts"]["new"] == 0


def test_default_baseline_falls_back_to_a_cancelled_run_when_no_finished_one_has_it(tmp_path: Path) -> None:
    _run(tmp_path, "r-cancelled", "2026-09-20T00:00:00Z", "cancelled", {_DIM: [_v("M-REU-1")]})
    _run(tmp_path, "r-curr", "2026-09-26T00:00:00Z", "done", {_DIM: [_v("M-REU-1")]})

    out = diff_runs(tmp_path, _PROJECT, "r-curr", None)

    assert out["dimensions"][_DIM]["againstRunId"] == "r-cancelled"


def test_no_baseline_is_signalled_per_dimension(tmp_path: Path) -> None:
    _run(tmp_path, "r-curr", "2026-09-26T00:00:00Z", "done", {_DIM: [_v("M-REU-1")]})

    out = diff_runs(tmp_path, _PROJECT, "r-curr", None)

    assert out["dimensions"][_DIM]["againstRunId"] is None
    assert out["againstRunId"] is None
