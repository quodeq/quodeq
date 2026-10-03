"""Tests for subprocess.py: standards rendering and loading, with param overrides."""
from __future__ import annotations

import json

from quodeq.analysis.subprocess import load_standards_text, render_standards_grouped


# ---------------------------------------------------------------------------
# render_standards_grouped
# ---------------------------------------------------------------------------

class TestRenderStandardsGrouped:
    def test_returns_empty_for_no_principles(self):
        assert render_standards_grouped({}) == ""
        assert render_standards_grouped({"principles": []}) == ""

    def test_renders_json_array(self):
        data = {
            "principles": [
                {
                    "name": "Input Validation",
                    "requirements": [
                        {"id": "S-INP-1", "text": "Validate all inputs"},
                        {"id": "S-INP-2", "text": "Sanitize SQL"},
                    ],
                }
            ]
        }
        result = render_standards_grouped(data)
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["principle"] == "Input Validation"
        assert len(parsed[0]["requirements"]) == 2
        assert parsed[0]["requirements"][0]["id"] == "S-INP-1"

    def test_handles_missing_name(self):
        data = {"principles": [{"requirements": [{"id": "X-1", "text": "rule"}]}]}
        result = render_standards_grouped(data)
        parsed = json.loads(result)
        assert parsed[0]["principle"] == "Unknown"

    def test_resolves_default_params_when_no_overrides(self):
        """With no override file, placeholders must be replaced by defaults — no raw templates in output."""
        data = {
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
        result = render_standards_grouped(data, overrides=None)
        parsed = json.loads(result)
        rule = parsed[0]["requirements"][0]["rule"]
        assert "{max_lines}" not in rule, f"raw placeholder still present: {rule!r}"
        assert "50" in rule

    def test_resolves_overridden_value(self):
        """With an override, the tuned value appears in the emitted text."""
        data = {
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
        result = render_standards_grouped(data, overrides={"M-ANA-2": {"max_lines": 80}})
        parsed = json.loads(result)
        rule = parsed[0]["requirements"][0]["rule"]
        assert "80" in rule
        assert "{max_lines}" not in rule


# ---------------------------------------------------------------------------
# load_standards_text (override threading)
# ---------------------------------------------------------------------------

class TestLoadStandardsTextOverrides:
    _DIM = {
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

    def test_no_override_file_uses_default(self, tmp_path):
        """No placeholder braces in output when analyzed repo has no override file."""
        (tmp_path / "compiled").mkdir()
        (tmp_path / "compiled" / "maintainability.json").write_text(json.dumps(self._DIM))
        result = load_standards_text(tmp_path / "compiled", "maintainability", overrides=None)
        assert "{max_lines}" not in result
        assert "50" in result

    def test_override_value_appears_in_text(self, tmp_path):
        """When an override is supplied, the overridden value appears in the emitted text."""
        (tmp_path / "compiled").mkdir()
        (tmp_path / "compiled" / "maintainability.json").write_text(json.dumps(self._DIM))
        result = load_standards_text(
            tmp_path / "compiled", "maintainability",
            overrides={"M-ANA-2": {"max_lines": 75}},
        )
        assert "75" in result
        assert "{max_lines}" not in result


# ---------------------------------------------------------------------------
# load_standards_text
# ---------------------------------------------------------------------------

class TestLoadStandardsText:
    def test_returns_empty_when_no_dir(self):
        assert load_standards_text(None, "security") == ""

    def test_returns_empty_when_no_dimension(self, tmp_path):
        assert load_standards_text(tmp_path, None) == ""

    def test_loads_from_json(self, tmp_path):
        data = {
            "principles": [
                {"name": "Auth", "requirements": [{"id": "A-1", "text": "Use tokens"}]}
            ]
        }
        (tmp_path / "security.json").write_text(json.dumps(data))
        result = load_standards_text(tmp_path, "security")
        assert "Auth" in result
        assert "A-1" in result

    def test_falls_back_to_md(self, tmp_path):
        md_content = "# Security Standards\n- Validate inputs"
        (tmp_path / "security.md").write_text(md_content)
        result = load_standards_text(tmp_path, "security")
        assert "Security Standards" in result

    def test_truncates_long_json_standards(self, tmp_path):
        data = {
            "principles": [
                {"name": f"Principle{i}", "requirements": [{"id": f"P-{i}", "text": "x" * 5000}]}
                for i in range(20)
            ]
        }
        (tmp_path / "security.json").write_text(json.dumps(data))
        result = load_standards_text(tmp_path, "security")
        assert "[... standards truncated for context limits ...]" in result

    def test_truncates_long_md_standards(self, tmp_path):
        (tmp_path / "security.md").write_text("x" * 60_000)
        result = load_standards_text(tmp_path, "security")
        assert "[... standards truncated for context limits ...]" in result

    def test_returns_empty_on_invalid_json(self, tmp_path):
        (tmp_path / "security.json").write_text("not valid json{{{")
        result = load_standards_text(tmp_path, "security")
        # Falls back to md, which doesn't exist
        assert result == ""

    def test_returns_empty_when_files_missing(self, tmp_path):
        assert load_standards_text(tmp_path, "nonexistent") == ""

    def test_non_utf8_md_warns_and_returns_empty(self, tmp_path, caplog):
        """The .md fallback's except narrows to (OSError, UnicodeDecodeError)
        and logs at warning (not debug): a read failure here changes what
        the model sees, so it must not be silent by default."""
        (tmp_path / "security.md").write_bytes(b"\xff\xfe not utf-8")
        with caplog.at_level("WARNING"):
            result = load_standards_text(tmp_path, "security")
        assert result == ""
        assert any("standards text file unreadable" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# render_standards_grouped: malformed compiled-JSON shapes
# ---------------------------------------------------------------------------

class TestRenderStandardsGroupedMalformedShapes:
    def test_list_data_returns_str_without_raising(self):
        result = render_standards_grouped([])
        assert isinstance(result, str)
        assert result == ""

    def test_non_dict_principle_and_non_dict_id_are_skipped(self):
        data = {"principles": [1, {"requirements": [{"text": "x"}]}]}
        result = render_standards_grouped(data)
        assert isinstance(result, str)

    def test_non_list_principles_returns_str_without_raising(self):
        result = render_standards_grouped({"principles": "x"})
        assert isinstance(result, str)
        assert result == ""

    def test_compiled_json_list_falls_back_to_md(self, tmp_path):
        """A compiled .json file whose top level is a list renders empty,
        so load_standards_text falls back to the .md text."""
        (tmp_path / "security.json").write_text(json.dumps([]))
        (tmp_path / "security.md").write_text("# Security Standards\n- Validate inputs")
        result = load_standards_text(tmp_path, "security")
        assert "Security Standards" in result

    def test_none_requirements_treated_as_empty(self):
        data = {"principles": [{"name": "P", "requirements": None}]}
        result = render_standards_grouped(data)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed[0]["requirements"] == []

    def test_non_list_scalar_requirements_treated_as_empty(self):
        data = {"principles": [{"name": "P", "requirements": "not-a-list"}]}
        result = render_standards_grouped(data)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed[0]["requirements"] == []
