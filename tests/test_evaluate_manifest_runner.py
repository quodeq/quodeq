from codecompass.evaluate.lib.manifest_runner import build_project_context


def test_build_project_context():
    manifest = {
        "project": {"name": "demo"},
        "targets": [
            {"name": "api", "path": "services/api", "discipline": "backend"},
            {"name": "web", "path": "apps/web", "discipline": "frontend"},
        ],
    }

    context = build_project_context(manifest)
    assert "multi-target project" in context
    assert "api (services/api) -> backend" in context
    assert "web (apps/web) -> frontend" in context
