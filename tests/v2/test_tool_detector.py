from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="detector/judge code removed in PR2")

from pathlib import Path
from unittest.mock import patch

import pytest

from codecompass.v2.engine.detectors.tool import ToolDetector, register_parser, _PARSER_REGISTRY
from codecompass.v2.engine.finding import Finding


@pytest.fixture(autouse=True)
def _clean_registry():
    """Ensure tests don't leak parser registrations."""
    original = _PARSER_REGISTRY.copy()
    yield
    _PARSER_REGISTRY.clear()
    _PARSER_REGISTRY.update(original)


def _dummy_parser(stdout: str, config: dict) -> list[Finding]:
    return [Finding(
        rule="test:dummy",
        label="Dummy finding",
        file="test.ts",
        dimension="security",
        detector="tool:test",
    )]


def test_parser_registration():
    register_parser("test_tool", _dummy_parser)
    assert "test_tool" in _PARSER_REGISTRY


def test_missing_parser_raises():
    detector = ToolDetector()
    config = {"tool": "nonexistent", "command": "echo hi", "optional": False}
    with pytest.raises(ValueError, match="No parser registered"):
        detector.run(Path("."), config)


def test_missing_parser_optional_returns_empty():
    detector = ToolDetector()
    config = {"tool": "nonexistent", "command": "echo hi", "optional": True}
    findings = detector.run(Path("."), config)
    assert findings == []


def test_tool_runs_command_and_parses(tmp_path):
    register_parser("echo_tool", _dummy_parser)
    detector = ToolDetector()
    config = {"tool": "echo_tool", "command": "echo test", "optional": False}
    findings = detector.run(tmp_path, config)
    assert len(findings) == 1
    assert findings[0].rule == "test:dummy"


def test_timeout_returns_empty(tmp_path):
    register_parser("slow_tool", _dummy_parser)
    detector = ToolDetector()
    config = {"tool": "slow_tool", "command": "sleep 10", "optional": False, "timeout": 1}
    findings = detector.run(tmp_path, config)
    assert findings == []


def test_nonzero_exit_still_parses(tmp_path):
    """Tools like ESLint return non-zero when they find issues."""
    register_parser("failing_tool", _dummy_parser)
    detector = ToolDetector()
    config = {"tool": "failing_tool", "command": "exit 1", "optional": False}
    # The subprocess returns exit code 1 but stdout is empty, parser still runs
    findings = detector.run(tmp_path, config)
    assert len(findings) == 1
