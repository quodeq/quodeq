"""Tests for multi-dimension refs loading."""
import json

from quodeq.data.fs import standards_loader
from quodeq.data.fs.standards_loader import (
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


class TestMultiLoadersListStandardsDirsOnce:
    """known_dimension_ids() globs compiled_dir/evaluators_dir from scratch;
    the _multi loaders must compute it once per call, not once per dimension.
    """

    def test_refs_multi_lists_once(self, tmp_path, monkeypatch):
        _write_compiled(tmp_path, "security", "S-CON-1", "Confidentiality")
        _write_compiled(tmp_path, "reliability", "R-1", "Resilience")
        calls = []
        real = standards_loader.known_dimension_ids
        monkeypatch.setattr(
            standards_loader, "known_dimension_ids",
            lambda *a, **k: (calls.append(a), real(*a, **k))[1],
        )
        refs = standards_loader.load_compiled_refs_multi(tmp_path, ["security", "reliability"])
        assert len(calls) == 1
        assert "S-CON-1" in refs and "R-1" in refs

    def test_requirements_multi_lists_once(self, tmp_path, monkeypatch):
        _write_compiled(tmp_path, "security", "S-CON-1", "Confidentiality")
        _write_compiled(tmp_path, "reliability", "R-1", "Resilience")
        calls = []
        real = standards_loader.known_dimension_ids
        monkeypatch.setattr(
            standards_loader, "known_dimension_ids",
            lambda *a, **k: (calls.append(a), real(*a, **k))[1],
        )
        reqs = standards_loader.load_compiled_requirements_multi(tmp_path, ["security", "reliability"])
        assert len(calls) == 1
        assert "S-CON-1" in reqs and "R-1" in reqs

    def test_multi_loaders_accept_a_mixed_case_dimension_id(self, tmp_path):
        # services/standards_library.py writes "{id}.json" verbatim from
        # user-supplied JSON, so a custom evaluator's filename can be
        # mixed-case. is_known_dimension() lower-cases both sides for the
        # membership check; the request is passed through unchanged, so
        # requesting the id in the file's own case still resolves the
        # path on every filesystem (ext4 is case-sensitive, APFS isn't).
        _write_compiled(tmp_path, "MyDimension", "X-1", "Custom")
        refs = standards_loader.load_compiled_refs_multi(tmp_path, ["MyDimension"])
        assert "X-1" in refs
        reqs = standards_loader.load_compiled_requirements_multi(tmp_path, ["MyDimension"])
        assert "X-1" in reqs
