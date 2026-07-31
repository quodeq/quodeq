"""Tests for multi-dimension refs loading."""
import json
from pathlib import Path

from quodeq.core.standards.refs import (
    load_compiled_refs_multi,
    load_compiled_requirements_multi,
)


def _write_compiled(tmp_path, dim, req_id, principle_name="Test"):
    data = {
        "id": dim,
        "principles": [{
            "name": principle_name,
            "source": "iso25010",
            "requirements": [{
                "id": req_id,
                "source": "iso25010",
                "text": f"Test requirement for {dim}",
                "refs": [{"source": "cwe", "id": "123", "url": "https://example.com", "name": "Test CWE"}],
            }],
        }],
    }
    (tmp_path / f"{dim}.json").write_text(json.dumps(data))


class TestLoadCompiledRefsMulti:
    def test_loads_from_multiple_dimensions(self, tmp_path):
        _write_compiled(tmp_path, "security", "S-CON-1", "Confidentiality")
        _write_compiled(tmp_path, "maintainability", "M-MOD-1", "Modularity")

        refs = load_compiled_refs_multi(tmp_path, ["security", "maintainability"])
        assert "S-CON-1" in refs
        assert "M-MOD-1" in refs

    def test_empty_dimensions_list(self, tmp_path):
        refs = load_compiled_refs_multi(tmp_path, [])
        assert refs == {}


class TestLoadCompiledRequirementsMulti:
    def test_loads_from_multiple_dimensions(self, tmp_path):
        _write_compiled(tmp_path, "security", "S-CON-1", "Confidentiality")
        _write_compiled(tmp_path, "maintainability", "M-MOD-1", "Modularity")

        reqs = load_compiled_requirements_multi(tmp_path, ["security", "maintainability"])
        assert "S-CON-1" in reqs
        assert reqs["S-CON-1"]["principle"] == "Confidentiality"
        assert "M-MOD-1" in reqs
        assert reqs["M-MOD-1"]["principle"] == "Modularity"

    def test_empty_dimensions_list(self, tmp_path):
        reqs = load_compiled_requirements_multi(tmp_path, [])
        assert reqs == {}

    def test_missing_dimension_file_skipped(self, tmp_path):
        """Requesting a dimension whose compiled JSON doesn't exist returns empty without error."""
        _write_compiled(tmp_path, "security", "S-CON-1", "Confidentiality")
        reqs = load_compiled_requirements_multi(tmp_path, ["security", "nonexistent"])
        assert "S-CON-1" in reqs
        assert all(k.startswith("S-") for k in reqs)
