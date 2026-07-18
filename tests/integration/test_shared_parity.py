"""Parity: a published project must render identically from the shared
clone as it does from the local evaluations root.

This is the core correctness guarantee of the shared-results feature: the
same project, run, and dismissal state must produce the SAME numbers
whether read through /api/projects/... (local reports_dir) or
/api/shared/projects/... (the shared clone). Any divergence here is a real
bug in root-threading -- either a missing publish-allowlist file, index
drift, or score-cache contamination -- and must be fixed at the root, never
by loosening the assertions below.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.services.dismissed import dismiss_finding
from quodeq.services.shared_publish import publish_project
from quodeq.services.shared_repo import sync_shared_index
from quodeq.services.shared_settings import SharedSettings, write_settings

_PROJECT = "proj-a"
_RUN = "run-1"

# Two findings in Security, one in Reliability. The Security/R1 finding gets
# dismissed via actions.jsonl so parity covers dismissal-aware scoring on
# both the violations list and the recomputed score/grade.
_SECURITY_VIOLATIONS = [
    dict(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="weak hash", req="R1", severity="high",
    ),
    dict(
        practice_id="P2", verdict="violation", dimension="Security",
        file="b.py", line=20, reason="sql injection", req="R2", severity="critical",
    ),
]
_RELIABILITY_VIOLATIONS = [
    dict(
        practice_id="P3", verdict="violation", dimension="Reliability",
        file="c.py", line=5, reason="no retry", req="R3", severity="medium",
    ),
]

_DISMISSED = {"req": "R1", "file": "a.py", "line": 10}


def _eval_json(dimension: str, violations: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "dimension": dimension,
        "project": _PROJECT,
        "runId": _RUN,
        "overallScore": "6.0/10",
        "overallGrade": "Fair",
        "principles": [{
            "name": "Integrity", "score": "6.0/10", "grade": "Fair",
            "violations": [], "compliance": [],
        }],
        "violations": [
            {
                "principle": "Integrity", "req": v["req"], "file": v["file"],
                "line": v["line"], "severity": v["severity"], "reason": v["reason"],
                "title": v["reason"].title(),
            }
            for v in violations
        ],
        "compliance": [],
    }


def _make_origin(tmp_path: Path) -> str:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    return f"file://{origin}"


@pytest.fixture()
def real_project_fixture(tmp_path, monkeypatch):
    """Build a real project under a temp evaluations root: one completed
    run with findings across 2 dimensions (via events.jsonl), frozen
    evaluation/<dim>.json files, evidence, dimensions.json, status.json
    (state=done), and a project actions.jsonl dismissing one finding.

    Returns the local evaluations root Path.
    """
    local_root = tmp_path / "local-evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(local_root))

    project_dir = local_root / _PROJECT
    run_dir = project_dir / _RUN

    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evaluation").mkdir(parents=True)

    (project_dir / "repository_info.json").write_text(
        json.dumps({"name": _PROJECT}), encoding="utf-8",
    )
    # Project-level scan.json (quick-scan coverage metadata). Publishing must
    # carry it into the clone (Finding 3) so the dashboard's coverage header
    # (totalFiles/analyzedFiles, added by _fs_reports._enrich_with_coverage)
    # is identical on both sides instead of only appearing locally.
    (project_dir / "scan.json").write_text(
        json.dumps({"total_files": 42, "code_files": 30}), encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps({"state": "done", "schema_version": 2}), encoding="utf-8",
    )
    (run_dir / "dimensions.json").write_text("{}", encoding="utf-8")
    (run_dir / "evidence" / "manifest.json").write_text("{}", encoding="utf-8")

    writer = EventLogWriter(run_dir / "events.jsonl")
    for violation in (*_SECURITY_VIOLATIONS, *_RELIABILITY_VIOLATIONS):
        writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(**violation)))

    (run_dir / "evaluation" / "Security.json").write_text(
        json.dumps(_eval_json("Security", _SECURITY_VIOLATIONS)), encoding="utf-8",
    )
    (run_dir / "evaluation" / "Reliability.json").write_text(
        json.dumps(_eval_json("Reliability", _RELIABILITY_VIOLATIONS)), encoding="utf-8",
    )

    dismiss_finding(project_dir, _DISMISSED)

    return local_root


@pytest.fixture()
def shared_clone_fixture(tmp_path, monkeypatch, real_project_fixture):
    """Publish real_project_fixture into a bare origin, clone it as the
    shared repo, and sync its index -- same recipe as
    tests/services/test_shared_repo.py::test_readable_and_index_sync_on_published_clone
    and tests/api/test_routes_shared_read.py::shared_clone_fixture.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")

    url = _make_origin(tmp_path)
    publish_project(_PROJECT, url, evaluations_root=real_project_fixture)
    sync_shared_index(url)
    write_settings(SharedSettings(url=url))
    return url


@pytest.fixture()
def client():
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c


def test_dashboard_parity_local_vs_shared(client, real_project_fixture, shared_clone_fixture):
    """Publish a fixture project, then compare local vs shared responses.

    No field-level normalization is needed here: neither payload encodes the
    evaluations root path (dashboard/scores/violations carry project-relative
    data -- run ids, dimension names, file/line/req identities -- never an
    absolute reports_dir/eval_root string), so a plain equality check is the
    real assertion, not a stand-in for one that had to be loosened.
    """
    local = client.get(f"/api/projects/{_PROJECT}/dashboard?run={_RUN}").get_json()
    shared = client.get(f"/api/shared/projects/{_PROJECT}/dashboard?run={_RUN}").get_json()
    assert shared == local

    # Finding 3: the published clone must carry the project-level scan.json
    # too, so the coverage header the local dashboard derives from it
    # (totalFiles) is present and identical on the shared side as well --
    # not merely absent-on-both-sides, which the blanket equality above
    # alone wouldn't distinguish from a fixed publish allowlist.
    assert local["totalFiles"] == 42
    assert shared["totalFiles"] == 42

    # The dismissed R1/a.py:10 finding must not appear on either side.
    dims = {d["dimension"]: d for d in local["dimensions"]}
    security_reqs = {v["req"] for v in dims["Security"]["violations"]}
    assert "R1" not in security_reqs
    assert "R2" in security_reqs


def test_scores_parity_local_vs_shared(client, real_project_fixture, shared_clone_fixture):
    local_scores = client.get(f"/api/projects/{_PROJECT}/scores").get_json()
    shared_scores = client.get(f"/api/shared/projects/{_PROJECT}/scores").get_json()
    assert shared_scores == local_scores


def test_violations_parity_local_vs_shared(client, real_project_fixture, shared_clone_fixture):
    """The dismissal must suppress the same finding on both sides.

    The local route takes run_id as a URL path segment
    (/runs/<run_id>/violations); the shared mirror takes it as a query
    param (?run=) -- see the shared-route module docstring for why the
    two shapes diverge. The response bodies are otherwise identical.
    """
    local = client.get(f"/api/projects/{_PROJECT}/runs/{_RUN}/violations").get_json()
    shared = client.get(f"/api/shared/projects/{_PROJECT}/violations?run={_RUN}").get_json()
    assert shared == local
    assert local["total"] == 2  # R2 (Security) + R3 (Reliability); R1 dismissed
