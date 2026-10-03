"""POST /api/projects for a git URL is a 202 job; GET /api/projects/clone-status reports its slot."""
from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import pytest

from quodeq.api.app import create_app
from quodeq.core.types.sync_phase import SyncPhase
from quodeq.data.fs.git_progress import ProgressUpdate
from quodeq.services import project_clone_job
from quodeq.services.base import CreateProjectResult, CreateProjectStatus
from quodeq.services.project_clone_job import CloneStatus
from quodeq.shared.git_errors import GitFailureKind

_ORIGIN = {"Origin": "http://localhost"}
_URL = "https://github.com/o/repo.git"
_CREATE = "quodeq.services.filesystem.FilesystemActionProvider.create_project"
_INVALIDATE = "quodeq.services.filesystem.FilesystemActionProvider.invalidate_projects_cache"


def _inline(target):
    target()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evaluations"))
    monkeypatch.setattr(project_clone_job, "_default_status", CloneStatus())
    monkeypatch.setattr(project_clone_job, "spawn_daemon", _inline)  # same seam as the inline_clone_job fixture
    home = tmp_path.resolve()
    monkeypatch.setattr("quodeq.api.routes_project_create.default_clone_root", lambda env=None: home / "repos")
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c, patch("pathlib.Path.home", new=classmethod(lambda cls: home)):
        yield c


@pytest.fixture()
def created():
    """Patch create_project to record its spec, report both callbacks, and succeed."""
    specs = []

    def fake(self, reports_root, spec):
        specs.append(spec)
        if spec.progress is not None:
            spec.progress(ProgressUpdate(percent=50, bytes=10))
            spec.on_phase(SyncPhase.READING)
        return CreateProjectResult(status=CreateProjectStatus.CREATED, project_id="p-1", scan_data={"total_files": 2})
    with patch(_CREATE, new=fake), patch(_INVALIDATE) as invalidate:
        yield specs, invalidate


def test_url_repo_starts_a_clone_job_and_answers_202(client, created, tmp_path):
    specs, invalidate = created
    r = client.post("/api/projects", json={"repo": _URL}, headers=_ORIGIN)
    assert r.status_code == HTTPStatus.ACCEPTED
    body = r.get_json()
    assert body["started"] is True and body["repo"] == _URL
    assert body["dest"] == str(tmp_path.resolve() / "repos" / "repo")
    assert specs[0].clone_dest == str(tmp_path.resolve() / "repos") and specs[0].ephemeral is False
    assert invalidate.call_count == 1
    assert (tmp_path / "repos").is_dir()


def test_finished_job_slot_carries_the_created_project(client, created):
    client.post("/api/projects", json={"repo": _URL}, headers=_ORIGIN)
    snap = client.get("/api/projects/clone-status").get_json()
    assert (snap["kind"], snap["state"], snap["phase"], snap["percent"]) == ("clone", "done", "done", 100)
    assert (snap["projectId"], snap["projectName"], snap["scanData"]) == ("p-1", "repo", {"total_files": 2})
    assert snap["finishedAt"] is not None


def test_explicit_clone_dest_is_used_for_the_job(client, created, tmp_path):
    parent = tmp_path / "code"
    parent.mkdir()
    r = client.post("/api/projects", json={"repo": _URL, "cloneDest": str(parent)}, headers=_ORIGIN)
    assert r.status_code == HTTPStatus.ACCEPTED
    assert r.get_json()["dest"] == str(parent / "repo")


def test_job_records_downloading_and_reading_phases(client):
    seen = []

    def fake(self, reports_root, spec):
        def slot():
            return project_clone_job.get_clone_status()
        spec.progress(ProgressUpdate(percent=50, bytes=10))
        seen.append((slot()["phase"], slot()["percent"]))
        spec.on_phase(SyncPhase.READING)
        seen.append(slot()["phase"])
        return CreateProjectResult(status=CreateProjectStatus.CREATED, project_id="p")
    with patch(_CREATE, new=fake), patch(_INVALIDATE):
        client.post("/api/projects", json={"repo": _URL}, headers=_ORIGIN)
    assert seen == [(SyncPhase.DOWNLOADING, 50), SyncPhase.READING]


def test_failed_clone_lands_in_the_slot_and_forgets_the_url(client, monkeypatch):
    forgotten = []
    monkeypatch.setattr("quodeq.api.routes_project_clone.forget_url", forgotten.append)
    result = CreateProjectResult(
        status=CreateProjectStatus.CLONE_FAILED, message="Clone failed",
        clone_error_kind=GitFailureKind.NOT_FOUND, clone_stderr="fatal: repository not found",
    )
    with patch(_CREATE, return_value=result):
        r = client.post("/api/projects", json={"repo": _URL}, headers=_ORIGIN)
    assert r.status_code == HTTPStatus.ACCEPTED
    snap = client.get("/api/projects/clone-status").get_json()
    assert snap["state"] == "error" and snap["code"] == "REPO_NOT_FOUND"
    assert "repository not found" in snap["detail"]
    assert forgotten == [_URL]


def test_duplicate_project_lands_as_project_exists_with_the_existing_id(client):
    result = CreateProjectResult(status=CreateProjectStatus.DUPLICATE, message="exists", existing_project_id="old-1")
    with patch(_CREATE, return_value=result):
        client.post("/api/projects", json={"repo": _URL}, headers=_ORIGIN)
    snap = client.get("/api/projects/clone-status").get_json()
    assert snap["code"] == "PROJECT_EXISTS" and snap["detail"] == "old-1"


def test_second_clone_while_running_is_409(client, monkeypatch):
    status = CloneStatus()
    status.claim("u", "d")
    monkeypatch.setattr(project_clone_job, "_default_status", status)
    r = client.post("/api/projects", json={"repo": "https://github.com/o/other.git"}, headers=_ORIGIN)
    assert r.status_code == HTTPStatus.CONFLICT and r.get_json()["code"] == "CLONE_IN_PROGRESS"


def test_failing_to_spawn_is_500_clone_start_failed(client, monkeypatch):
    def refuse(target):
        raise RuntimeError("no threads")
    monkeypatch.setattr(project_clone_job, "spawn_daemon", refuse)
    r = client.post("/api/projects", json={"repo": _URL}, headers=_ORIGIN)
    assert r.status_code == HTTPStatus.INTERNAL_SERVER_ERROR and r.get_json()["code"] == "CLONE_START_FAILED"


def test_local_folder_stays_synchronous(client, tmp_path):
    repo = tmp_path / "local"
    repo.mkdir()
    r = client.post("/api/projects", json={"repo": str(repo)}, headers=_ORIGIN)
    assert r.status_code == HTTPStatus.OK and "projectId" in r.get_json()


def test_ephemeral_url_stays_synchronous(client, created):
    r = client.post("/api/projects", json={"repo": _URL, "ephemeral": True}, headers=_ORIGIN)
    assert r.status_code == HTTPStatus.OK and r.get_json()["projectId"] == "p-1"


def test_clone_status_is_idle_by_default(client):
    snap = client.get("/api/projects/clone-status").get_json()
    assert snap["state"] == "idle" and snap["finishedAt"] is None and snap["projectId"] is None
