from pathlib import Path
from codecompass.engine.plugin_loader import load_plugin

PLUGIN_DIR = Path(__file__).parent.parent.parent / "evaluators" / "typescript"


def test_plugin_loads():
    plugin = load_plugin(PLUGIN_DIR)
    assert plugin["id"] == "typescript"
    assert ".ts" in plugin["detects"]["extensions"]


def test_plugin_has_knowledge():
    assert (PLUGIN_DIR / "knowledge" / "practices.json").exists()
    assert (PLUGIN_DIR / "knowledge" / "analysis.md").exists()
