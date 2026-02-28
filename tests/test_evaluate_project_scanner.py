from pathlib import Path

from codecompass.evaluate.lib.project_scanner import scan_project


def test_scan_project_root_match(tmp_path: Path):
    (tmp_path / "next.config.js").write_text("module.exports = {}")

    manifest = scan_project(str(tmp_path))

    assert manifest["version"] == 1
    assert manifest["project"]["name"] == tmp_path.name
    assert manifest["targets"] == [
        {
            "name": tmp_path.name,
            "path": ".",
            "discipline": "frontend_nextjs",
            "dimensions": "all",
        }
    ]


def test_scan_project_subdir_match(tmp_path: Path):
    apps = tmp_path / "apps" / "web"
    apps.mkdir(parents=True)
    (apps / "package.json").write_text("{}")

    manifest = scan_project(str(tmp_path))

    assert manifest["project"]["name"] == tmp_path.name
    assert manifest["targets"] == [
        {
            "name": "web",
            "path": "apps/web",
            "discipline": "frontend_react",
            "dimensions": "all",
        }
    ]
