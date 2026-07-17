"""End-to-end publish flow against a local bare repo."""
import json
import subprocess
from pathlib import Path

import pytest

from quodeq.services.shared_publish import PublishError, publish_project
from quodeq.services.shared_repo import shared_repo_path


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


def test_publish_bootstraps_and_pushes(tmp_path):
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)
    count = publish_project("proj-uuid-1", url, evaluations_root=root)
    assert count == 1
    # verify the remote actually received the content
    verify = tmp_path / "verify"
    subprocess.run(["git", "clone", url, str(verify)], check=True, capture_output=True)
    assert (verify / "quodeq.json").exists()
    assert (verify / "evaluations" / "proj-uuid-1" / "run-1" / "status.json").exists()


def test_publish_is_idempotent_no_empty_commit(tmp_path):
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)
    publish_project("proj-uuid-1", url, evaluations_root=root)
    publish_project("proj-uuid-1", url, evaluations_root=root)  # must not raise
    repo = shared_repo_path(url)
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip().splitlines()
    assert len(log) == 1  # second publish added no commit


def test_publish_into_foreign_repo_refused(tmp_path):
    url = _bare_origin(tmp_path)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", url, str(seed)], check=True, capture_output=True)
    (seed / "README.md").write_text("existing project")
    for cmd in (["git", "add", "."], ["git", "commit", "-m", "x"], ["git", "push", "origin", "HEAD"]):
        subprocess.run(cmd, cwd=seed, check=True, capture_output=True)
    root = _local_project(tmp_path)
    with pytest.raises(PublishError):
        publish_project("proj-uuid-1", url, evaluations_root=root)


def test_publish_race_rebase_retry(tmp_path):
    url = _bare_origin(tmp_path)
    root = _local_project(tmp_path)
    publish_project("proj-uuid-1", url, evaluations_root=root)
    # someone else pushes meanwhile
    other = tmp_path / "other"
    subprocess.run(["git", "clone", url, str(other)], check=True, capture_output=True)
    (other / "evaluations" / "other-proj").mkdir(parents=True)
    (other / "evaluations" / "other-proj" / "repository_info.json").write_text("{}")
    for cmd in (["git", "add", "."], ["git", "commit", "-m", "other"], ["git", "push", "origin", "HEAD"]):
        subprocess.run(cmd, cwd=other, check=True, capture_output=True)
    # our clone is now behind; a new run appears locally
    run2 = root / "proj-uuid-1" / "run-2"
    (run2 / "evidence").mkdir(parents=True)
    (run2 / "status.json").write_text(json.dumps({"state": "done", "schema_version": 2}))
    (run2 / "dimensions.json").write_text("{}")
    (run2 / "events.jsonl").write_text("{}\n")
    # publish must succeed via rebase retry, and the other project must survive (additive)
    publish_project("proj-uuid-1", url, evaluations_root=root)
    verify = tmp_path / "verify2"
    subprocess.run(["git", "clone", url, str(verify)], check=True, capture_output=True)
    assert (verify / "evaluations" / "proj-uuid-1" / "run-2").exists()
    assert (verify / "evaluations" / "other-proj").exists()
