"""``diff_runs`` reads two runs' reports and classifies per dimension."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.events.models import FindingDismissed, FindingDismissedEvent
from quodeq.data.actions_log import ActionLogWriter
from quodeq.services.run_diff import LIST_CAP, diff_runs

_PROJECT = "p"
_PREV = "2026-09-20T00-00-00"
_CURR = "2026-09-26T00-00-00"
_DIM = "maintainability"


def _report(run_dir: Path, violations: list[dict], compliance: list[dict]) -> None:
    (run_dir / "evaluation").mkdir(parents=True, exist_ok=True)
    (run_dir / "evaluation" / f"{_DIM}.json").write_text(json.dumps({
        "dimension": _DIM, "principles": [], "violations": violations, "compliance": compliance,
    }), encoding="utf-8")
    (run_dir / "status.json").write_text(json.dumps({
        "state": "done", "started_at": f"{run_dir.name[:10]}T00:00:00Z"}), encoding="utf-8")


def _v(req: str, file: str, line: int, snippet: str, severity: str = "minor") -> dict:
    return {"req": req, "file": file, "line": line, "snippet": snippet, "severity": severity,
            "principle": "P"}


def test_diff_runs_per_dimension(tmp_path: Path) -> None:
    prev = tmp_path / _PROJECT / _PREV
    curr = tmp_path / _PROJECT / _CURR
    _report(prev, [_v("M-REU-1", "b.py", 2, "dup()")], [])
    _report(curr, [_v("M-ANA-9", "a.py", 5, "long")],
            [{"req": "M-REU-1", "file": "b.py", "line": 1, "principle": "P"}])
    out = diff_runs(tmp_path, _PROJECT, _CURR, _PREV)
    dim = out["dimensions"][_DIM]
    assert out["againstRunId"] == _PREV
    assert dim["counts"] == {"carried": 0, "same": 0, "moved": 0, "new": 1,
                             "resolved": 1, "notReevaluated": 0}
    assert dim["types"] == {"closed": ["M-REU-1"], "opened": ["M-ANA-9"],
                            "perReq": {"M-ANA-9": [0, 1], "M-REU-1": [1, 0]}}
    assert [f["req"] for f in dim["new"]] == ["M-ANA-9"]
    assert LIST_CAP > 0


def test_diff_runs_without_a_previous_run_reports_everything_new(tmp_path: Path) -> None:
    curr = tmp_path / _PROJECT / _CURR
    _report(curr, [_v("M-ANA-9", "a.py", 5, "long")], [])
    out = diff_runs(tmp_path, _PROJECT, _CURR, None)
    assert out["againstRunId"] is None
    assert out["dimensions"][_DIM]["counts"]["new"] == 1


def test_dismissed_findings_are_left_out_of_both_sides(tmp_path: Path) -> None:
    """A dismissed finding is neither "new" on every run nor "resolved" when
    it stops being reported; the project's dismissals apply to the diff."""
    prev = tmp_path / _PROJECT / _PREV
    curr = tmp_path / _PROJECT / _CURR
    _report(prev, [_v("M-REU-1", "b.py", 2, "dup()")], [])
    _report(curr, [_v("M-ANA-9", "a.py", 5, "long")],
            [{"req": "M-REU-1", "file": "b.py", "line": 1, "principle": "P"}])
    writer = ActionLogWriter(tmp_path / _PROJECT)
    writer.emit(FindingDismissedEvent(payload=FindingDismissed(req="M-ANA-9", file="a.py", line=5)))
    writer.emit(FindingDismissedEvent(payload=FindingDismissed(req="M-REU-1", file="b.py", line=2)))

    dim = diff_runs(tmp_path, _PROJECT, _CURR, _PREV)["dimensions"][_DIM]

    assert dim["counts"] == {"carried": 0, "same": 0, "moved": 0, "new": 0,
                             "resolved": 0, "notReevaluated": 0}
    assert dim["types"]["perReq"] == {}
