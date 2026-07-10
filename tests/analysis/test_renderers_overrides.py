"""Tests for per-project threshold overrides in prompt renderers."""
import json

from quodeq.analysis.prompts._renderers import (
    render_compact_standards,
    render_compiled_standards,
)

DIMENSION = {
    "id": "maintainability",
    "name": "Maintainability",
    "principles": [{
        "name": "Analyzability",
        "requirements": [{
            "id": "M-ANA-2",
            "text": "Functions MUST NOT exceed {max_lines} lines",
            "params": {"max_lines": {"label": "Max function lines", "type": "int",
                                     "default": 50, "min": 10, "max": 500}},
        }],
    }],
}


def _write_dim(tmp_path):
    (tmp_path / "maintainability.json").write_text(json.dumps(DIMENSION))
    return tmp_path


def test_compact_renders_default_without_overrides(tmp_path):
    out = render_compact_standards(_write_dim(tmp_path), "maintainability")
    assert "Functions MUST NOT exceed 50 lines" in out
    assert "{max_lines}" not in out


def test_compact_renders_override(tmp_path):
    out = render_compact_standards(
        _write_dim(tmp_path), "maintainability",
        overrides={"M-ANA-2": {"max_lines": 60}})
    assert "Functions MUST NOT exceed 60 lines" in out


def test_compiled_renders_override(tmp_path):
    out = render_compiled_standards(
        _write_dim(tmp_path), "maintainability",
        overrides={"M-ANA-2": {"max_lines": 60}})
    assert "- **M-ANA-2**: Functions MUST NOT exceed 60 lines" in out
