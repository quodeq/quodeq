from pathlib import Path
from codecompass.v2.engine.plugin_loader import load_plugin
from codecompass.v2.engine.detectors.grep import GrepDetector

PLUGIN_DIR = Path("evaluators/typescript")


def test_plugin_loads():
    plugin = load_plugin(PLUGIN_DIR)
    assert plugin["id"] == "typescript"
    assert ".ts" in plugin["detects"]["extensions"]


def test_plugin_has_knowledge():
    assert (PLUGIN_DIR / "knowledge" / "practices.json").exists()
    assert (PLUGIN_DIR / "knowledge" / "analysis.md").exists()


def test_plugin_scan_rules_run(tmp_path):
    (tmp_path / "bad.ts").write_text("const x = eval(input);")
    detector = GrepDetector()
    config = {"rules_file": str(PLUGIN_DIR / "scan_rules.ini")}
    findings = detector.run(tmp_path, config)
    assert len(findings) >= 1
