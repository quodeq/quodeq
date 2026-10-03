import subprocess

from tests.api._routes_shared_fixtures import _ORIGIN, _clean_publish_status, client  # noqa: F401
from tests.api.test_routes_shared_config import inline_connect  # noqa: F401 -- autouse fixture

_MESSAGE = "That folder is not a git repository. Run git init there first, or point at a bare repository."


def _bare(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True, timeout=30)
    return origin


def test_a_local_bare_repo_connects_and_reports_configured(client, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    url = (_bare(tmp_path)).as_uri()
    resp = client.put("/api/shared/config", json={"url": url}, headers=_ORIGIN)
    assert resp.status_code == 202
    status = client.get("/api/shared/status").get_json()
    assert status["connect"]["state"] == "done", status["connect"]
    assert status["configured"] is True


def test_a_plain_folder_is_a_400_not_a_git_repo(client, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "plain").mkdir()
    resp = client.put("/api/shared/config", json={"url": (tmp_path / 'plain').as_uri()}, headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "NOT_A_GIT_REPO"
    assert body["error"] == _MESSAGE
    assert str(tmp_path) not in body["error"]


def test_a_folder_outside_home_is_invalid_url(client, tmp_path, monkeypatch):
    (tmp_path / "home").mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    resp = client.put("/api/shared/config", json={"url": (_bare(tmp_path)).as_uri()}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_URL"


def test_probe_route_answers_not_a_git_repo_for_a_plain_folder(client, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "plain").mkdir()
    resp = client.post("/api/git/probe", json={"url": (tmp_path / 'plain').as_uri()}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "NOT_A_GIT_REPO"
