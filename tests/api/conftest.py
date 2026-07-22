"""Shared fixtures for tests/api/*.

``shared_clone_fixture`` builds a REAL published shared-repo clone (bare
origin + publish_project + sync_shared_index) and points settings at it —
the recipe every shared-clone integration test in this directory needs.
Moved here from ``test_routes_shared_read.py`` (its original home) so
``test_assistant_shared_sessions.py`` can reuse it without duplicating the
fixture (Task 6, Step 0).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.services.shared_publish import publish_project
from quodeq.services.shared_repo import (
    ensure_shared_clone,
    shared_evaluations_root,
    shared_repo_path,
    sync_shared_index,
)
from quodeq.services.shared_settings import SharedSettings, write_settings

_VIOLATION = dict(
    practice_id="P1", verdict="violation", dimension="Security",
    file="a.py", line=10, reason="weak hash", req="R1", severity="high",
)

_EVAL_JSON = {
    "schema_version": 1,
    "dimension": "Security",
    "project": "proj-a",
    "runId": "run-1",
    "overallScore": "7.0/10",
    "overallGrade": "Good",
    "principles": [{"name": "Integrity", "score": "7.0/10", "grade": "Good", "violations": [], "compliance": []}],
    "violations": [{
        "principle": "Integrity", "req": "R1", "file": "a.py", "line": 10,
        "severity": "major", "reason": "bad", "title": "Bad",
    }],
    "compliance": [],
}


def _make_origin(tmp_path: Path) -> str:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    return f"file://{origin}"


@pytest.fixture()
def shared_clone_fixture(tmp_path, monkeypatch):
    """Build a real published shared-repo clone and point settings at it.

    Follows the same recipe as
    tests/services/test_shared_repo.py::test_readable_and_index_sync_on_published_clone:
    bare origin + publish_project + sync_shared_index. ``publish_project``'s
    staging allowlist (source-of-truth files only) never carries
    ``evaluation/<dim>.json`` — a real published run always has that
    directory empty — so a per-dimension eval file is written directly into
    the clone afterwards to exercise the dashboard/accumulated/dimension-eval/
    violations read paths (this task's job) against real content, without
    relitigating the publish allowlist (a prior task's decision).
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")

    url = _make_origin(tmp_path)
    # published.json's publishedBy comes from `git config user.name` in the
    # clone (GIT_AUTHOR_NAME/GIT_COMMITTER_NAME above only affect a commit's
    # recorded identity, not `git config` lookups) -- pin it on the clone's
    # LOCAL config so the "tester" assertion below is deterministic
    # regardless of the machine running the test.
    assert ensure_shared_clone(url) is not None
    subprocess.run(
        ["git", "config", "user.name", "tester"],
        cwd=shared_repo_path(url), check=True, capture_output=True,
    )
    local_root = tmp_path / "local-evaluations"
    project_dir = local_root / "proj-a"
    run_dir = project_dir / "run-1"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}", encoding="utf-8")
    (project_dir / "repository_info.json").write_text(
        json.dumps({"name": "proj-a", "originUrl": "https://github.com/example/proj-a.git"}), encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps({"state": "done", "schema_version": 2}), encoding="utf-8",
    )
    (run_dir / "dimensions.json").write_text("{}", encoding="utf-8")

    writer = EventLogWriter(run_dir / "events.jsonl")
    writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(**_VIOLATION)))

    publish_project("proj-a", url, evaluations_root=local_root)
    sync_shared_index(url)

    repo_run_dir = shared_evaluations_root(url) / "proj-a" / "run-1"
    (repo_run_dir / "evaluation").mkdir(parents=True, exist_ok=True)
    (repo_run_dir / "evaluation" / "Security.json").write_text(
        json.dumps(_EVAL_JSON), encoding="utf-8",
    )

    write_settings(SharedSettings(url=url))
    return url
