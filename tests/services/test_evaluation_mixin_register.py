import json
import subprocess
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


def test_register_url_rejects_private_address_before_clone(tmp_path, monkeypatch):
    """SSRF guard: a URL whose host is a private/link-local literal is rejected
    before git clone runs, matching the CLI prepare_repository path."""
    reports = tmp_path / "reports"
    reports.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    clone_calls = []

    def fake_clone(url, dest):
        clone_calls.append(url)
        Path(dest).mkdir(parents=True, exist_ok=True)
        (Path(dest) / "README.md").write_text("# fake\n")
        (Path(dest) / ".git").mkdir()

    with patch("quodeq.services.evaluation_mixin.run_git_clone", side_effect=fake_clone):
        with pytest.raises(ValueError, match="private"):
            _register_project(
                "https://169.254.169.254/latest/meta-data",
                None,
                str(reports),
                ephemeral=True,
            )

    assert clone_calls == [], "git clone must not run for a private-host URL"


def test_register_url_rejects_localhost_before_clone(tmp_path, monkeypatch):
    """A localhost URL is rejected by the SSRF guard before any clone."""
    reports = tmp_path / "reports"
    reports.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    clone_calls = []

    def fake_clone(url, dest):
        clone_calls.append(url)
        Path(dest).mkdir(parents=True, exist_ok=True)
        (Path(dest) / "README.md").write_text("# fake\n")
        (Path(dest) / ".git").mkdir()

    with patch("quodeq.services.evaluation_mixin.run_git_clone", side_effect=fake_clone):
        with pytest.raises(ValueError):
            _register_project(
                "https://localhost/git/repo.git",
                None,
                str(reports),
                ephemeral=True,
            )

    assert clone_calls == []


def test_start_evaluation_rejects_url_input(tmp_path):
    """start_evaluation no longer clones; URLs must already be registered as local."""
    from quodeq.services.base import EvaluationOptions
    from quodeq.services.evaluation_mixin import FsEvaluationMixin

    class _Stub(FsEvaluationMixin):
        _jobs = None
        _dispatcher = None

    with pytest.raises(ValueError, match="not supported"):
        _Stub().start_evaluation(
            "https://github.com/example/repo.git",
            str(tmp_path),
            EvaluationOptions(),
        )


class _FakeDispatcher:
    """Records dispatch calls without spawning a subprocess."""

    def __init__(self):
        self.calls = []

    def dispatch(self, cmd, *, cwd=None, env=None, ai_provider=None, ai_model=None):
        self.calls.append(cmd)
        return {"id": "fake-job"}


def _make_mixin():
    from quodeq.services.evaluation_mixin import FsEvaluationMixin

    mixin = FsEvaluationMixin()
    mixin._jobs = object()  # no set_reports_root attr -> guard skips it
    mixin._dispatcher = _FakeDispatcher()
    return mixin


def test_start_evaluation_stamps_onboarding_completed(tmp_path):
    """Starting an evaluation completes onboarding: the null field written at
    registration time must become a timestamp, otherwise the Projects page
    shows 'Resume setup' forever for wizard-created projects."""
    from quodeq.services.base import EvaluationOptions

    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    reports = tmp_path / "reports"
    reports.mkdir()
    uuid = _register_project(str(repo), None, str(reports))
    assert _read_info(reports, uuid)["onboardingCompletedAt"] is None

    _make_mixin().start_evaluation(str(repo), str(reports), EvaluationOptions())

    stamped = _read_info(reports, uuid)["onboardingCompletedAt"]
    assert isinstance(stamped, str) and stamped


def test_start_evaluation_preserves_existing_onboarding_stamp(tmp_path):
    """A later evaluation must not move an already-set completion timestamp."""
    from quodeq.services.base import EvaluationOptions

    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    reports = tmp_path / "reports"
    reports.mkdir()
    uuid = _register_project(str(repo), None, str(reports))
    info_path = reports / uuid / "repository_info.json"
    data = json.loads(info_path.read_text())
    data["onboardingCompletedAt"] = "2025-12-01T00:00:00Z"
    info_path.write_text(json.dumps(data))

    _make_mixin().start_evaluation(str(repo), str(reports), EvaluationOptions())

    assert _read_info(reports, uuid)["onboardingCompletedAt"] == "2025-12-01T00:00:00Z"


def test_register_url_repo_persists_origin_url(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    reports = tmp_path / "reports"
    reports.mkdir()
    url = "https://github.com/example/repo.git"

    def fake_clone(u, dest):
        dest.mkdir(parents=True)
        (dest / ".git").mkdir()
        (dest / "main.py").write_text("print('hi')\n")

    with patch("quodeq.services.evaluation_mixin.run_git_clone", side_effect=fake_clone):
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


def test_register_local_repo_without_remote_omits_origin_url(tmp_path):
    repo = tmp_path / "plain"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    reports = tmp_path / "reports"
    reports.mkdir()

    uuid = _register_project(str(repo), None, str(reports))

    assert "originUrl" not in _read_info(reports, uuid)
