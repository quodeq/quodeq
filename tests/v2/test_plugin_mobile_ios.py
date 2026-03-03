from __future__ import annotations

import json
from pathlib import Path

from codecompass.v2.engine.plugin_loader import load_plugin
from codecompass.v2.engine.schema_validator import validate_plugin_dir
from codecompass.v2.engine.detectors.grep import GrepDetector

PLUGIN_DIR = Path(__file__).parent.parent.parent / "evaluators" / "mobile_ios"


def test_plugin_loads():
    data = load_plugin(PLUGIN_DIR)
    assert data["id"] == "mobile_ios"


def test_plugin_has_knowledge():
    practices = json.loads((PLUGIN_DIR / "knowledge" / "practices.json").read_text())
    assert len(practices["practices"]) >= 3


def test_plugin_passes_validation():
    errors = validate_plugin_dir(PLUGIN_DIR)
    assert errors == {}, f"Validation errors: {errors}"


def test_scan_rules_detect_secrets(tmp_path):
    bad_file = tmp_path / "Config.swift"
    bad_file.write_text('let apiKey = "sk-prod-abc123xyz456789"\n')
    detector = GrepDetector()
    findings = detector.run(tmp_path, {"rules_file": str(PLUGIN_DIR / "scan_rules.ini")})
    assert any(f.cwe == 798 for f in findings)
