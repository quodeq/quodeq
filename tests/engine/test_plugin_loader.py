from pathlib import Path
from quodeq.engine.plugin_loader import discover_plugins, load_plugin

FIXTURES = Path(__file__).parent / "fixtures" / "evaluators"


def test_discovers_valid_plugin():
    plugins = discover_plugins(FIXTURES)
    assert len(plugins) == 1
    assert plugins[0]["id"] == "sample_plugin"


def test_ignores_cross_cutting_dir():
    plugins = discover_plugins(FIXTURES)
    ids = [p["id"] for p in plugins]
    assert "_cross_cutting" not in ids


def test_load_plugin_returns_path():
    plugin = load_plugin(FIXTURES / "sample_plugin")
    assert plugin["id"] == "sample_plugin"
    assert "detects" in plugin


def test_discover_empty_dir(tmp_path):
    assert discover_plugins(tmp_path) == []
