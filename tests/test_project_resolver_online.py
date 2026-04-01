import json
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
