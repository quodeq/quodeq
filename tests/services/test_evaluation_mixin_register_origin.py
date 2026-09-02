"""Tests for project_registration.py — originUrl persistence and credential
stripping.

Split from test_evaluation_mixin_register.py.
"""
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from quodeq.services.project_registration import register_project as _register_project


def _read_info(reports_root: Path, uuid: str) -> dict:
    return json.loads((reports_root / uuid / "repository_info.json").read_text())


def test_register_url_repo_persists_origin_url(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir()
    url = "https://github.com/example/repo.git"

    def fake_clone(u, dest):
        dest.mkdir(parents=True)
        (dest / ".git").mkdir()
        (dest / "main.py").write_text("print('hi')\n")

    with patch("quodeq.services.project_registration.run_git_clone", side_effect=fake_clone):
        uuid = _register_project(url, None, str(reports), ephemeral=True)

    assert _read_info(reports, uuid)["originUrl"] == url


def test_register_local_repo_persists_origin_remote(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/example/myrepo.git"],
        check=True, capture_output=True,
    )
    reports = tmp_path / "reports"
    reports.mkdir()

    uuid = _register_project(str(repo), None, str(reports))

    assert _read_info(reports, uuid)["originUrl"] == "https://github.com/example/myrepo.git"


def test_register_local_repo_strips_credentials_from_origin_url(tmp_path):
    """A credentialed origin remote (user:pass@ or token@) must never be
    persisted verbatim: repository_info.json is exposed via GET /api/projects
    and copied into the team-shared repo on publish."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "remote", "add", "origin",
            "https://user:ghp_supersecret@github.com/example/myrepo.git",
        ],
        check=True, capture_output=True,
    )
    reports = tmp_path / "reports"
    reports.mkdir()

    uuid = _register_project(str(repo), None, str(reports))

    persisted = _read_info(reports, uuid)["originUrl"]
    assert persisted == "https://github.com/example/myrepo.git"
    assert "ghp_supersecret" not in persisted
    assert "user:" not in persisted


def test_register_local_repo_strips_token_only_credential_from_origin_url(tmp_path):
    """Token-only userinfo (no colon) must also be stripped, not just user:pass."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "remote", "add", "origin",
            "https://ghp_supersecrettoken@github.com/example/myrepo.git",
        ],
        check=True, capture_output=True,
    )
    reports = tmp_path / "reports"
    reports.mkdir()

    uuid = _register_project(str(repo), None, str(reports))

    persisted = _read_info(reports, uuid)["originUrl"]
    assert persisted == "https://github.com/example/myrepo.git"
    assert "ghp_supersecrettoken" not in persisted


def test_register_local_repo_preserves_scp_style_origin_url(tmp_path):
    """scp-style remotes (git@host:org/repo.git) must persist unchanged: the
    leading `git@` there is a username convention, not a credential."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", str(repo), "remote", "add", "origin",
            "git@github.com:example/myrepo.git",
        ],
        check=True, capture_output=True,
    )
    reports = tmp_path / "reports"
    reports.mkdir()

    uuid = _register_project(str(repo), None, str(reports))

    assert _read_info(reports, uuid)["originUrl"] == "git@github.com:example/myrepo.git"


def test_register_local_repo_without_remote_omits_origin_url(tmp_path):
    repo = tmp_path / "plain"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    uuid = _register_project(str(repo), None, str(reports))

    assert "originUrl" not in _read_info(reports, uuid)
