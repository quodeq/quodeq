"""FilesystemActionProvider.create_project — QUODEQ_CLONES_DIR wiring.

create_project is the public entry point (the provider composition point)
that resolves the ephemeral-clone base directory: register_project /
_project_registration_steps never read QUODEQ_CLONES_DIR themselves (see
project_registration.py's module docstring / _resolve_target_path).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from quodeq.services.base import NewProjectSpec
from quodeq.services.filesystem import FilesystemActionProvider


def _fake_clone(_url: str, dest: Path) -> None:
    Path(dest).mkdir(parents=True, exist_ok=True)
    (Path(dest) / ".git").mkdir()
    (Path(dest) / "main.py").write_text("print('hi')\n")


def test_ephemeral_url_clone_lands_under_quodeq_clones_dir_env(tmp_path, monkeypatch):
    """No ``clones_dir=`` passed to the provider -- the real process env,
    through the public create_project() entry point, must still pick a
    QUODEQ_CLONES_DIR override."""
    reports = tmp_path / "reports"
    reports.mkdir()
    env_clones_dir = tmp_path / "custom-clones"
    monkeypatch.setenv("QUODEQ_CLONES_DIR", str(env_clones_dir))

    provider = FilesystemActionProvider(reports_root=reports)
    spec = NewProjectSpec("https://github.com/example/repo.git", None, ephemeral=True)

    with patch("quodeq.services._project_registration_steps.run_git_clone", side_effect=_fake_clone):
        result = provider.create_project(str(reports), spec)

    assert result.status == "created"
    assert result.project_id is not None
    clone_target = env_clones_dir / result.project_id
    assert clone_target.is_dir()
    assert (clone_target / "main.py").exists()


def test_explicit_provider_clones_dir_overrides_the_env(tmp_path, monkeypatch):
    """A caller-supplied clones_dir (the provider's own constructor override)
    wins over QUODEQ_CLONES_DIR, matching every other injected-env-var seam."""
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setenv("QUODEQ_CLONES_DIR", str(tmp_path / "from-env"))
    explicit_clones_dir = tmp_path / "from-constructor"

    provider = FilesystemActionProvider(reports_root=reports, clones_dir=explicit_clones_dir)
    spec = NewProjectSpec("https://github.com/example/repo.git", None, ephemeral=True)

    with patch("quodeq.services._project_registration_steps.run_git_clone", side_effect=_fake_clone):
        result = provider.create_project(str(reports), spec)

    assert result.status == "created"
    clone_target = explicit_clones_dir / result.project_id
    assert clone_target.is_dir()
