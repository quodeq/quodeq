import json
import subprocess
from pathlib import Path

from quodeq.data.fs.project_resolver import (
    ProjectIdentity,
    resolve_project_uuid,
    clear_index_cache,
)
from quodeq.services.filesystem import FilesystemActionProvider


def test_online_project_stores_url(tmp_path: Path) -> None:
    """An online project must store the original URL as its path."""
    clear_index_cache()
    identity = ProjectIdentity(
        project_name="shaka-player",
        repo_path="https://github.com/shaka-project/shaka-player",
        discipline=None,
        location="online",
    )
    project_uuid = resolve_project_uuid(tmp_path, identity)
    info = json.loads((tmp_path / project_uuid / "repository_info.json").read_text())
    assert info["path"] == "https://github.com/shaka-project/shaka-player"
    assert info["location"] == "online"


def test_online_project_with_temp_path_logs_warning(tmp_path: Path, capsys) -> None:
    """Creating an online project with a local path should log a warning."""
    clear_index_cache()
    identity = ProjectIdentity(
        project_name="shaka-player",
        repo_path="/private/var/folders/t2/xyz/shaka-player",
        discipline=None,
        location="online",
    )
    resolve_project_uuid(tmp_path, identity)
    captured = capsys.readouterr()
    assert "online project" in captured.err.lower()


def _create_online_project_with_temp_path(reports_dir: Path) -> str:
    """Helper: create a project with location=online but a local temp path (simulates the bug)."""
    import uuid as _uuid
    project_uuid = str(_uuid.uuid4())
    project_dir = reports_dir / project_uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "uuid": project_uuid,
        "name": "shaka-player",
        "discipline": None,
        "location": "online",
        "path": "/private/var/folders/t2/xyz/shaka-player",
    }
    (project_dir / "repository_info.json").write_text(json.dumps(info))
    return project_uuid


def _create_online_project_with_url(reports_dir: Path) -> str:
    """Helper: create a project with location=online and a proper URL path."""
    import uuid as _uuid
    project_uuid = str(_uuid.uuid4())
    project_dir = reports_dir / project_uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "uuid": project_uuid,
        "name": "shaka-player",
        "discipline": None,
        "location": "online",
        "path": "https://github.com/shaka-project/shaka-player",
    }
    (project_dir / "repository_info.json").write_text(json.dumps(info))
    return project_uuid


def test_get_project_info_detects_stale_online_path(tmp_path: Path) -> None:
    """get_project_info should flag online projects with non-URL paths."""
    project_uuid = _create_online_project_with_temp_path(tmp_path)
    provider = FilesystemActionProvider()
    info = provider.get_project_info(str(tmp_path), project_uuid)
    assert info is not None
    assert info["pathMissing"] is True


def test_get_project_info_valid_online_not_missing(tmp_path: Path) -> None:
    """Online project with a proper URL should have pathMissing=False."""
    project_uuid = _create_online_project_with_url(tmp_path)
    provider = FilesystemActionProvider()
    info = provider.get_project_info(str(tmp_path), project_uuid)
    assert info is not None
    assert info["pathMissing"] is False


def test_clone_to_local_updates_project(tmp_path: Path, monkeypatch) -> None:
    """clone_to_local should clone the repo and update repository_info.json."""
    project_uuid = _create_online_project_with_url(tmp_path)
    dest = tmp_path / "local_repos"
    dest.mkdir()

    def fake_run(cmd, check, **kwargs):
        clone_dest = Path(cmd[-1])
        clone_dest.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(subprocess, "run", fake_run)

    provider = FilesystemActionProvider()
    result = provider.clone_to_local(str(tmp_path), project_uuid, str(dest))
    assert result is not None
    assert result["location"] == "local"
    assert "shaka-player" in result["path"]
    assert Path(result["path"]).is_dir()

    info = json.loads((tmp_path / project_uuid / "repository_info.json").read_text())
    assert info["location"] == "local"
    assert info["path"] == result["path"]


def _create_local_project(reports_dir: Path, local_path: Path) -> str:
    """Helper: create a project with location=local."""
    import uuid as _uuid
    project_uuid = str(_uuid.uuid4())
    project_dir = reports_dir / project_uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    info = {
        "uuid": project_uuid,
        "name": "my-project",
        "discipline": None,
        "location": "local",
        "path": str(local_path),
    }
    (project_dir / "repository_info.json").write_text(json.dumps(info))
    return project_uuid


def test_clone_to_local_rejects_local_project(tmp_path: Path) -> None:
    """clone_to_local should return None for projects already local."""
    local_path = tmp_path / "existing"
    local_path.mkdir()
    project_uuid = _create_local_project(tmp_path, local_path)
    provider = FilesystemActionProvider()
    result = provider.clone_to_local(str(tmp_path), project_uuid, str(tmp_path / "dest"))
    assert result is None


def test_update_project_path_accepts_url(tmp_path: Path) -> None:
    """update_project_path should accept a URL for online projects."""
    project_uuid = _create_online_project_with_temp_path(tmp_path)
    provider = FilesystemActionProvider()
    ok = provider.update_project_path(
        str(tmp_path), project_uuid, "https://github.com/shaka-project/shaka-player"
    )
    assert ok is True
    info = json.loads((tmp_path / project_uuid / "repository_info.json").read_text())
    assert info["path"] == "https://github.com/shaka-project/shaka-player"
    assert info["location"] == "online"
