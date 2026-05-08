import json
import os
import time

import pytest


@pytest.fixture
def reports_with_project(tmp_path):
    """Helper: returns (reports_root, project_uuid, project_dir, write_info_fn)."""
    reports = tmp_path / "reports"
    reports.mkdir()
    project_uuid = "info-test-uuid"
    project_dir = reports / project_uuid
    project_dir.mkdir()

    def write_info(**fields):
        (project_dir / "repository_info.json").write_text(json.dumps(fields))

    return reports, project_uuid, project_dir, write_info


def test_info_includes_last_fetched_at_from_fetch_head(tmp_path, reports_with_project):
    from quodeq.services._fs_projects import get_project_info
    reports, project_uuid, _, write_info = reports_with_project
    repo = tmp_path / "myrepo"
    (repo / ".git").mkdir(parents=True)
    fetch_head = repo / ".git" / "FETCH_HEAD"
    fetch_head.write_text("")
    target_mtime = time.time() - 3 * 86400  # 3 days ago
    os.utime(fetch_head, (target_mtime, target_mtime))

    write_info(location="local", path=str(repo), ephemeral=False)

    info = get_project_info(str(reports), project_uuid)
    assert info is not None
    assert "lastFetchedAt" in info
    assert info["lastFetchedAt"] is not None
    assert info["evaluable"] is True
    assert info["ephemeral"] is False


def test_info_falls_back_to_head_when_fetch_head_missing(tmp_path, reports_with_project):
    from quodeq.services._fs_projects import get_project_info
    reports, project_uuid, _, write_info = reports_with_project
    repo = tmp_path / "freshclone"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    write_info(location="local", path=str(repo))

    info = get_project_info(str(reports), project_uuid)
    assert info is not None
    assert info["lastFetchedAt"] is not None


def test_info_evaluable_false_for_deleted_ephemeral(tmp_path, reports_with_project):
    from quodeq.services._fs_projects import get_project_info
    reports, project_uuid, _, write_info = reports_with_project
    write_info(location="local", ephemeral=True, path=str(tmp_path / "no-such-dir"))

    info = get_project_info(str(reports), project_uuid)
    assert info is not None
    assert info["evaluable"] is False
    assert info["ephemeral"] is True


def test_info_no_git_dir_returns_none_last_fetched(tmp_path, reports_with_project):
    from quodeq.services._fs_projects import get_project_info
    reports, project_uuid, _, write_info = reports_with_project
    repo = tmp_path / "no-git-repo"
    repo.mkdir()
    write_info(location="local", path=str(repo))

    info = get_project_info(str(reports), project_uuid)
    assert info is not None
    assert info["lastFetchedAt"] is None
    assert info["evaluable"] is True  # dir exists even though no .git
