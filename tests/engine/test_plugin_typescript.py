import pytest

from quodeq.config.paths import default_paths
from quodeq.engine.plugin_loader import load_plugin


@pytest.fixture()
def plugin_dir():
    path = default_paths().evaluators_dir / "typescript"
    if not path.exists():
        pytest.skip("typescript evaluator not installed")
    return path


def test_plugin_loads(plugin_dir):
    plugin = load_plugin(plugin_dir)
    assert plugin["id"] == "typescript"
    assert ".ts" in plugin["detects"]["extensions"]


def test_plugin_has_analysis_md(plugin_dir):
    assert (plugin_dir / "knowledge" / "analysis.md").exists()
