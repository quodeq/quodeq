import json

from codecompass.config.actions import run_generate_practices
from codecompass.config.paths import ConfigPaths


def test_run_generate_practices_uses_topics(tmp_path, monkeypatch):
    practices_dir = tmp_path / "practices" / "backend"
    practices_dir.mkdir(parents=True)
    (practices_dir / "solid.json").write_text(json.dumps({"metadata": {"topic": "SOLID"}}))
    (practices_dir / "error_handling.json").write_text("{}")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "disciplines.conf").write_text("[backend]\nlanguage=Python\ncategory=backend\n")

    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(
        "codecompass.config.practices_manager.generate_practices_for_discipline",
        fake_generate,
    )

    paths = ConfigPaths.from_root(tmp_path)
    run_generate_practices("backend", paths)

    assert captured["topics"] == ["error_handling", "SOLID"]
    assert captured["language"] == "Python"
