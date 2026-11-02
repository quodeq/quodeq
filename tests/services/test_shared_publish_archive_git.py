"""Publishing archived runs end to end: the commit holds the run files publish wrote, nothing else."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quodeq.data.fs.run_archive import ARCHIVE_FILENAME, RESTORED_STAMP, archive_run, is_archived
from quodeq.data.fs.shared_repo import ensure_shared_clone, shared_repo_path
from quodeq.services import shared_publish
from quodeq.services.shared_publish import PublishError, publish_project
from tests.services._archive_fixtures import PROJECT, corrupt, make_run
from tests.services._shared_publish_git_fixtures import _bare_origin, _git_identity  # noqa: F401 -- fixture
from tests._timeouts import budget

_EVIDENCE = "evidence/security_evidence.jsonl"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True,
                          timeout=budget(30)).stdout


def _run(root: Path, run_id: str, *, days: int = 300) -> Path:
    run = make_run(root, run_id, days=days)
    (run / "evidence").mkdir(exist_ok=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    (run / _EVIDENCE).write_text('{"snippet": "x"}\n')
    return run


def _publish(url: str, root: Path) -> Path:
    publish_project(PROJECT, url, evaluations_root=root)
    return shared_repo_path(url)


def _head_files(repo: Path) -> list[str]:
    return [line for line in _git(repo, "show", "--name-only", "--format=", "HEAD").splitlines() if line]


def _rel(run_id: str, name: str) -> str:
    return f"evaluations/{PROJECT}/{run_id}/{name}"


@pytest.fixture
def setup(tmp_path):
    return _bare_origin(tmp_path), tmp_path / "local"


def test_republishing_runs_shared_in_full_form_after_archiving_them_changes_nothing(setup):
    url, root = setup
    runs = [_run(root, "run-a"), _run(root, "run-b", days=200)]
    repo = _publish(url, root)
    head = _git(repo, "rev-parse", "HEAD")
    for run in runs:
        archive_run(run)
    _publish(url, root)
    assert _git(repo, "rev-parse", "HEAD") == head
    assert not list((repo / "evaluations" / PROJECT).rglob(ARCHIVE_FILENAME))
    assert all(is_archived(run) and not (run / RESTORED_STAMP).exists() for run in runs)


def test_an_archived_run_new_to_the_repo_is_committed_in_archive_form(setup):
    url, root = setup
    run = _run(root, "run-a")
    archive_run(run)
    packed = (run / ARCHIVE_FILENAME).read_bytes()
    repo = _publish(url, root)
    files = _head_files(repo)
    assert {_rel("run-a", n) for n in (ARCHIVE_FILENAME, "scalars.json", "precedents.json")} <= set(files)
    assert _rel("run-a", "events.jsonl") not in files and _rel("run-a", _EVIDENCE) not in files
    assert is_archived(run) and (run / ARCHIVE_FILENAME).read_bytes() == packed
    assert not (run / RESTORED_STAMP).exists() and not (run / "events.jsonl").exists()


def test_republishing_an_unchanged_archive_form_run_makes_no_commit(setup):
    url, root = setup
    archive_run(_run(root, "run-a"))
    repo = _publish(url, root)
    head = _git(repo, "rev-parse", "HEAD")
    _publish(url, root)
    assert _git(repo, "rev-parse", "HEAD") == head


def test_leftovers_in_the_clone_never_reach_the_commit(setup, monkeypatch):
    url, root = setup
    archive_run(_run(root, "run-a"))
    _run(root, "run-b", days=200)
    repo = _publish(url, root)
    full = repo / "evaluations" / PROJECT / "run-b"
    (full / "evaluation.db").write_text("tracked")
    _git(repo, "add", "-f", "--", _rel("run-b", "evaluation.db"))
    _git(repo, "commit", "-qm", "a database someone force-added")
    _git(repo, "push", "-q", "origin", "HEAD")
    _run(root, "run-c", days=10)
    real = shared_publish.stage_project

    def plant_then_stage(project_dir, dest, **opts):
        archived, full = dest / "run-a", dest / "run-b"
        (archived / "events.jsonl").write_text("restored in the clone\n")
        (archived / "evaluation.db-wal").write_text("wal")
        (archived / RESTORED_STAMP).write_text("stamp")
        (full / "evaluation.db").write_text("rebuilt")
        (dest / "stray.txt").write_text("untracked")
        return real(project_dir, dest, **opts)

    monkeypatch.setattr(shared_publish, "stage_project", plant_then_stage)
    _publish(url, root)
    files = _head_files(repo)
    assert _rel("run-c", "events.jsonl") in files
    assert [f for f in files if "/run-a/" in f or "/run-b/" in f or f.endswith("stray.txt")] == []


def test_a_corrupt_local_archive_fails_the_publish_and_stays_as_it_was(setup):
    url, root = setup
    run = _run(root, "run-a")
    corrupt(run)
    before = (run / ARCHIVE_FILENAME).read_bytes()
    with pytest.raises(PublishError):
        publish_project(PROJECT, url, evaluations_root=root)
    assert (run / ARCHIVE_FILENAME).read_bytes() == before


def test_runs_publish_when_git_would_ignore_their_files(setup):
    url, root = setup
    archive_run(_run(root, "run-a"))
    _run(root, "run-b", days=200)
    repo = ensure_shared_clone(url)
    exclude = repo / ".git" / "info" / "exclude"
    exclude.write_text(exclude.read_text() + "*.gz\n*.jsonl\n")
    _publish(url, root)
    files = _head_files(repo)
    assert {_rel("run-a", ARCHIVE_FILENAME), _rel("run-b", "events.jsonl"), _rel("run-b", _EVIDENCE)} <= set(files)


def test_a_linked_project_folder_in_the_clone_is_refused_before_any_write(setup, tmp_path, monkeypatch):
    url, root = setup
    _run(root, "run-a")
    outside = tmp_path / "outside"
    outside.mkdir()
    real = shared_publish.stage_project

    def link_then_stage(project_dir, dest, **opts):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(outside, target_is_directory=True)
        return real(project_dir, dest, **opts)

    monkeypatch.setattr(shared_publish, "stage_project", link_then_stage)
    with pytest.raises(PublishError, match="link"):
        publish_project(PROJECT, url, evaluations_root=root)
    assert list(outside.iterdir()) == []


def test_a_linked_run_folder_in_the_clone_is_refused_before_any_write(setup, tmp_path, monkeypatch):
    url, root = setup
    _run(root, "run-a")
    outside = tmp_path / "outside"
    outside.mkdir()
    real = shared_publish.stage_project

    def link_then_stage(project_dir, dest, **opts):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "run-a").symlink_to(outside, target_is_directory=True)
        return real(project_dir, dest, **opts)

    monkeypatch.setattr(shared_publish, "stage_project", link_then_stage)
    with pytest.raises(PublishError, match="link"):
        publish_project(PROJECT, url, evaluations_root=root)
    assert list(outside.iterdir()) == []
