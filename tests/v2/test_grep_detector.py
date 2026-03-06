import pytest

pytestmark = pytest.mark.skip(reason="detector/judge code removed in PR2")

from pathlib import Path
from codecompass.v2.engine.detectors.grep import GrepDetector

FIXTURES = Path(__file__).parent / "fixtures"


def test_grep_detector_finds_eval():
    detector = GrepDetector()
    config = {"rules_file": str(FIXTURES / "scan_rules.ini")}
    findings = detector.run(FIXTURES / "sample_src", config)
    assert len(findings) >= 1
    assert any(f.rule == "cwe_95_eval" for f in findings)
    assert any(f.cwe == 95 for f in findings)
    assert any("bad.ts" in f.file for f in findings)


def test_grep_detector_returns_empty_for_clean_src(tmp_path):
    (tmp_path / "clean.ts").write_text("const x = 1;")
    detector = GrepDetector()
    config = {"rules_file": str(FIXTURES / "scan_rules.ini")}
    findings = detector.run(tmp_path, config)
    assert findings == []
