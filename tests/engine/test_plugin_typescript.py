from quodeq.config.paths import default_paths
from quodeq.engine.plugin_loader import load_plugin

PLUGIN_DIR = default_paths().evaluators_dir / "typescript"


def test_plugin_loads():
    plugin = load_plugin(PLUGIN_DIR)
    assert plugin["id"] == "typescript"
    assert ".ts" in plugin["detects"]["extensions"]


def test_plugin_has_analysis_md():
    assert (PLUGIN_DIR / "knowledge" / "analysis.md").exists()
