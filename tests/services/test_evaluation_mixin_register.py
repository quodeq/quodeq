import json
from pathlib import Path
from unittest.mock import patch
import pytest
from quodeq.services.evaluation_mixin import _register_project


def _read_info(reports_root: Path, uuid: str) -> dict:
    return json.loads((reports_root / uuid / "repository_info.json").read_text())


def test_register_local_path_scans_in_place(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    uuid = _register_project(str(repo), None, str(reports))

    info = _read_info(reports, uuid)
    assert info["location"] == "local"
    assert info["path"] == str(repo.resolve())
    assert (reports / uuid / "scan.json").exists()


def test_register_url_clones_to_dest_then_scans(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    clone_dest = tmp_path / "code"
    clone_dest.mkdir()

    def fake_clone(url, dest):
        Path(dest).mkdir(parents=True, exist_ok=True)
        (Path(dest) / "README.md").write_text("# fake\n")
        (Path(dest) / ".git").mkdir()

    with patch("quodeq.services.evaluation_mixin.run_git_clone", side_effect=fake_clone):
        uuid = _register_project(
            "https://github.com/example/repo.git",
            None,
            str(reports),
            clone_dest=str(clone_dest),
        )

    info = _read_info(reports, uuid)
    assert info["location"] == "local"
    assert info["path"].startswith(str(clone_dest))
    assert info.get("ephemeral") is False
    assert (reports / uuid / "scan.json").exists()


def test_register_url_ephemeral_clones_under_clones_root(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    def fake_clone(url, dest):
        Path(dest).mkdir(parents=True, exist_ok=True)
        (Path(dest) / "README.md").write_text("# fake\n")
        (Path(dest) / ".git").mkdir()

    with patch("quodeq.services.evaluation_mixin.run_git_clone", side_effect=fake_clone):
        uuid = _register_project(
            "https://github.com/example/repo.git",
            None,
            str(reports),
            ephemeral=True,
        )

    info = _read_info(reports, uuid)
    assert info["location"] == "local"
    assert info["ephemeral"] is True
    expected_root = fake_home / ".quodeq" / "clones" / uuid
    assert Path(info["path"]) == expected_root


def test_register_url_clone_failure_raises(tmp_path):
    """run_git_clone raises CloneError on failure (Task A8 contract)."""
    from quodeq.services._fs_clone import CloneError

    reports = tmp_path / "reports"
    reports.mkdir()
    clone_dest = tmp_path / "code"
    clone_dest.mkdir()

    with patch(
        "quodeq.services.evaluation_mixin.run_git_clone",
        side_effect=CloneError("network", "git clone failed (network)"),
    ):
        with pytest.raises(CloneError):
            _register_project(
                "https://github.com/example/repo.git",
                None,
                str(reports),
                clone_dest=str(clone_dest),
            )


def test_register_url_without_dest_or_ephemeral_raises(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    with pytest.raises(ValueError, match="clone_dest"):
        _register_project("https://github.com/example/repo.git", None, str(reports))


def test_register_url_clone_dest_must_exist(tmp_path):
    """Pre-flight rejects a non-existent clone_dest before any side effects."""
    reports = tmp_path / "reports"
    reports.mkdir()
    nonexistent = tmp_path / "no-such-dir"

    with pytest.raises(FileNotFoundError, match="clone destination"):
        _register_project(
            "https://github.com/example/repo.git",
            None,
            str(reports),
            clone_dest=str(nonexistent),
        )

    # Verify nothing was created under the missing path
    assert not nonexistent.exists()
