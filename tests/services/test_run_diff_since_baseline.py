"""``sinceBaseline`` scopes new / resolved / majors delta to the files that changed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import quodeq.services.run_diff as run_diff_module
from quodeq.services.run_diff import diff_runs

_PROJECT = "p"
_PREV, _CURR = "r-prev", "r-curr"
_DIM = "maintainability"
_SHA_A, _SHA_B = "a" * 40, "b" * 40


def _run(root: Path, run_id: str, started_at: str, sha: str | None, violations: list[dict]) -> None:
    run_dir = root / _PROJECT / run_id
    (run_dir / "evaluation").mkdir(parents=True)
    (run_dir / "evaluation" / f"{_DIM}.json").write_text(json.dumps({
        "dimension": _DIM, "principles": [], "violations": violations, "compliance": []}),
        encoding="utf-8")
    status = {"state": "done", "started_at": started_at}
    if sha:
        status["commit_sha"] = sha
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")


def _v(req: str, file: str, severity: str = "minor") -> dict:
    return {"req": req, "file": file, "line": 1, "snippet": f"{req} in {file}", "severity": severity}


@pytest.fixture
def scoped(monkeypatch):
    """Pretend the project is a local checkout where only a.py changed."""
    monkeypatch.setattr(run_diff_module, "local_repo_root", lambda reports_root, project: Path("/repo"))
    monkeypatch.setattr(
        run_diff_module, "changed_files",
        lambda root, a, b: None if not (a and b) else (set() if a == b else {"a.py"}),
    )


def test_since_baseline_counts_only_findings_in_changed_files(tmp_path: Path, scoped) -> None:
    _run(tmp_path, _PREV, "2026-09-20T00:00:00Z", _SHA_A,
         [_v("M-REU-1", "b.py", "major"), _v("M-ANA-9", "a.py")])
    _run(tmp_path, _CURR, "2026-09-26T00:00:00Z", _SHA_B,
         [_v("M-MDF-1", "a.py", "major"), _v("M-TST-5", "c.py")])

    since = diff_runs(tmp_path, _PROJECT, _CURR, _PREV)["dimensions"][_DIM]["sinceBaseline"]

    assert since["scope"] == "changed-files" and since["changedFiles"] == 1
    assert since["counts"] == {"new": 1, "resolved": 1}
    assert [f["req"] for f in since["new"]] == ["M-MDF-1"]
    assert [f["req"] for f in since["resolved"]] == ["M-ANA-9"]
    assert since["majorsDelta"] == 1


def test_since_baseline_same_sha_is_empty(tmp_path: Path, scoped) -> None:
    _run(tmp_path, _PREV, "2026-09-20T00:00:00Z", _SHA_A, [_v("M-REU-1", "b.py")])
    _run(tmp_path, _CURR, "2026-09-26T00:00:00Z", _SHA_A, [_v("M-ANA-9", "a.py")])

    since = diff_runs(tmp_path, _PROJECT, _CURR, _PREV)["dimensions"][_DIM]["sinceBaseline"]

    assert (since["scope"], since["changedFiles"], since["counts"]) == (
        "changed-files", 0, {"new": 0, "resolved": 0})


def test_since_baseline_without_sha_uses_all_files(tmp_path: Path, scoped) -> None:
    _run(tmp_path, _PREV, "2026-09-20T00:00:00Z", None, [_v("M-REU-1", "b.py")])
    # b.py is read again (it holds a finding), so the old finding there counts as resolved.
    _run(tmp_path, _CURR, "2026-09-26T00:00:00Z", _SHA_B, [_v("M-ANA-9", "a.py"), _v("M-TST-5", "b.py")])

    since = diff_runs(tmp_path, _PROJECT, _CURR, _PREV)["dimensions"][_DIM]["sinceBaseline"]

    assert since["scope"] == "all" and since["changedFiles"] is None
    assert since["counts"] == {"new": 2, "resolved": 1}
