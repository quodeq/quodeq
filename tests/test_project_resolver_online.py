import json
from pathlib import Path

from quodeq.data.fs.project_resolver import (
    ProjectIdentity,
    resolve_project_uuid,
    clear_index_cache,
)


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
