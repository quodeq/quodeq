from pathlib import Path
from quodeq.api.app import create_app


def test_create_app_sweeps_orphaned_clones(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".quodeq" / "clones" / "orphan").mkdir(parents=True)
    (fake_home / ".quodeq" / "clones" / "orphan" / "file").write_text("x")
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    create_app()

    assert not (fake_home / ".quodeq" / "clones" / "orphan").exists()


def test_create_app_handles_missing_clones_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    # No ~/.quodeq/clones dir at all - must not raise.
    create_app()
