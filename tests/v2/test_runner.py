from __future__ import annotations

import json
from pathlib import Path

import pytest

from codecompass.v2.engine.runner import run, RunConfig


def _make_plugin_dir(base: Path) -> Path:
    """Create a minimal valid typescript plugin in a temp dir."""
    plugin_dir = base / "evaluators" / "typescript"
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "plugin.json").write_text(json.dumps({
        "id": "typescript",
        "name": "TypeScript",
        "version": "1.0.0",
        "engine_version": ">=2.0.0",
        "detects": {"extensions": [".ts"]},
    }))

    (plugin_dir / "dimensions.json").write_text(json.dumps({
        "applies": [{"id": "security", "weight": 1.2}],
    }))

    (plugin_dir / "detectors.json").write_text(json.dumps([
        {"type": "grep", "rules": "scan_rules.ini"},
    ]))

    (plugin_dir / "scan_rules.ini").write_text(
        "[cwe_95_eval]\n"
        "label=CWE-95: eval()\n"
        "cwe=95\n"
        "dimension=security\n"
        "command=grep -rn \"eval(\" {src} --include=\"*.ts\"\n"
        "format=file_list\n"
    )

    knowledge = plugin_dir / "knowledge"
    knowledge.mkdir()
    (knowledge / "practices.json").write_text(json.dumps({
        "runtime": "typescript",
        "version": "1.0.0",
        "practices": [{
            "id": "ts-001",
            "title": "Avoid eval()",
            "cwe": 95,
            "dimension": "security",
            "severity": "high",
            "bad": "eval(x)",
            "good": "JSON.parse(x)",
            "explanation": "eval is dangerous",
        }],
    }))

    (knowledge / "analysis.md").write_text("# Analysis\nLook for eval().\n")

    return base / "evaluators"


def test_run_end_to_end_with_mock_ai(tmp_path):
    evaluators_dir = _make_plugin_dir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.ts").write_text("const x = eval(input);\n")

    mock_output = json.dumps({
        "practice_id": "ts-001",
        "verdict": "violation",
        "file": str(src / "app.ts"),
        "line": 1,
        "severity": "high",
        "reason": "eval with user input",
        "dimension": "security",
    })

    def mock_ai(prompt):
        return (mock_output, None)

    config = RunConfig(
        src=src,
        plugin_id="typescript",
        evaluators_dir=evaluators_dir,
        source_file_count=1,
        ai_caller=mock_ai,
    )
    evidence = run(config)
    assert evidence.plugin_id == "typescript"
    assert "ts-001" in evidence.principles
    assert len(evidence.principles["ts-001"].violations) == 1


def test_detector_finds_eval(tmp_path):
    evaluators_dir = _make_plugin_dir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "bad.ts").write_text("const result = eval(userInput);\n")

    from codecompass.v2.engine.runner import _run_detectors

    plugin_dir = evaluators_dir / "typescript"
    detectors_config = json.loads((plugin_dir / "detectors.json").read_text())
    findings = _run_detectors(detectors_config, src, plugin_dir)
    assert len(findings) >= 1
    assert any(f.cwe == 95 for f in findings)


def test_empty_project(tmp_path):
    evaluators_dir = _make_plugin_dir(tmp_path)
    src = tmp_path / "src"
    src.mkdir()

    def mock_ai(prompt):
        return ("", None)

    config = RunConfig(
        src=src,
        plugin_id="typescript",
        evaluators_dir=evaluators_dir,
        source_file_count=0,
        ai_caller=mock_ai,
    )
    evidence = run(config)
    # Practices are seeded even when the judge returns nothing
    for pe in evidence.principles.values():
        assert pe.violations == []
        assert pe.compliance == []
        assert pe.metrics.get("no_evidence") is True


def test_unknown_plugin_error(tmp_path):
    evaluators_dir = tmp_path / "evaluators"
    evaluators_dir.mkdir()
    src = tmp_path / "src"
    src.mkdir()

    config = RunConfig(
        src=src,
        plugin_id="nonexistent",
        evaluators_dir=evaluators_dir,
    )
    with pytest.raises(ValueError, match="not found"):
        run(config)
