"""Shared bare-origin / local-project builders and the git identity fixture for tests/services/test_shared_publish_git*.py."""
import json
import subprocess
from pathlib import Path

import pytest


def _bare_origin(tmp_path: Path) -> str:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    return f"file://{origin}"


def _local_project(tmp_path: Path) -> Path:
    root = tmp_path / "evaluations"
    project = root / "proj-uuid-1"
    run = project / "run-1"
    (run / "evidence").mkdir(parents=True)
    (project / "repository_info.json").write_text('{"name":"demo"}')
    (run / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run / "dimensions.json").write_text("{}")
    (run / "events.jsonl").write_text("{}\n")
    (run / "evidence" / "manifest.json").write_text("{}")
    return root


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
