import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from compile_standards import build_cwe_index, report_gaps, compile_dimension


def test_build_cwe_index_from_iso(tmp_path):
    """CWE index extracts CWEs grouped by principle from ISO 25010."""
    iso_file = tmp_path / "iso25010" / "maintainability.json"
    iso_file.parent.mkdir(parents=True)
    iso_file.write_text(json.dumps({
        "id": "maintainability",
        "sub_characteristics": [
            {
                "name": "Modularity",
                "requirements": [
                    {"id": "M-MOD-1", "text": "Complexity MUST be ≤10", "cwe": [1121]}
                ]
            }
        ]
    }))
    cisq_file = tmp_path / "cisq" / "maintainability.json"
    cisq_file.parent.mkdir(parents=True)
    cisq_file.write_text(json.dumps({
        "cwes": [
            {"id": 1121, "name": "Excessive Complexity", "requirement": "Complexity MUST be ≤10"}
        ]
    }))

    index = build_cwe_index(tmp_path, "maintainability")
    assert "Modularity" in index
    assert 1121 in index["Modularity"]
    entry = index["Modularity"][1121]
    assert entry["refs"][0]["source"] == "iso25010"
    assert entry["refs"][0]["ref"] == "M-MOD-1"
    assert any(r["source"] == "cisq" for r in entry["refs"])


def test_build_cwe_index_attaches_asvs_for_security(tmp_path):
    """ASVS refs are attached to security CWEs that overlap."""
    iso_file = tmp_path / "iso25010" / "security.json"
    iso_file.parent.mkdir(parents=True)
    iso_file.write_text(json.dumps({
        "id": "security",
        "sub_characteristics": [{
            "name": "Integrity",
            "requirements": [
                {"id": "S-INT-2", "text": "SQL queries MUST use parameterised statements", "cwe": [89]}
            ]
        }]
    }))
    cisq_file = tmp_path / "cisq" / "security.json"
    cisq_file.parent.mkdir(parents=True)
    cisq_file.write_text(json.dumps({
        "cwes": [{"id": 89, "name": "SQL Injection", "requirement": "SQL MUST use params"}]
    }))
    asvs_file = tmp_path / "asvs" / "level1.json"
    asvs_file.parent.mkdir(parents=True)
    asvs_file.write_text(json.dumps({
        "requirements": [
            {"id": "V5.3.4", "cwe": [89], "section": "Validation",
             "text": "Verify that database queries use parameterized queries"}
        ]
    }))

    index = build_cwe_index(tmp_path, "security")
    refs = index["Integrity"][89]["refs"]
    sources = [r["source"] for r in refs]
    assert "iso25010" in sources
    assert "cisq" in sources
    assert "asvs" in sources
    asvs_ref = next(r for r in refs if r["source"] == "asvs")
    assert asvs_ref["ref"] == "V5.3.4"
    assert asvs_ref["section"] == "Validation"


def test_report_gaps_finds_orphan_cwes(tmp_path):
    """Gaps reporter finds CISQ CWEs missing from ISO 25010."""
    iso_file = tmp_path / "iso25010" / "maintainability.json"
    iso_file.parent.mkdir(parents=True)
    iso_file.write_text(json.dumps({
        "id": "maintainability",
        "sub_characteristics": [{
            "name": "Modularity",
            "requirements": [{"id": "M-MOD-1", "text": "...", "cwe": [1121]}]
        }]
    }))
    cisq_file = tmp_path / "cisq" / "maintainability.json"
    cisq_file.parent.mkdir(parents=True)
    cisq_file.write_text(json.dumps({
        "cwes": [
            {"id": 1121, "name": "Complexity", "requirement": "..."},
            {"id": 9999, "name": "Orphan CWE", "requirement": "..."}
        ]
    }))

    gaps = report_gaps(tmp_path, "maintainability")
    assert len(gaps) == 1
    assert "9999" in gaps[0]
    assert "Orphan CWE" in gaps[0]


def test_compile_dimension_output_shape(tmp_path):
    """compile_dimension produces the expected output structure."""
    iso_file = tmp_path / "iso25010" / "reliability.json"
    iso_file.parent.mkdir(parents=True)
    iso_file.write_text(json.dumps({
        "id": "reliability",
        "name": "Reliability",
        "sub_characteristics": [{
            "name": "Fault Tolerance",
            "requirements": [
                {"id": "R-FT-1", "text": "Exceptions MUST be handled", "cwe": [390]}
            ]
        }]
    }))
    cisq_file = tmp_path / "cisq" / "reliability.json"
    cisq_file.parent.mkdir(parents=True)
    cisq_file.write_text(json.dumps({
        "cwes": [{"id": 390, "name": "Error Without Action", "requirement": "Errors MUST trigger handling"}]
    }))

    result = compile_dimension(tmp_path, "reliability")

    assert result["id"] == "reliability"
    assert result["name"] == "Reliability"
    assert "iso25010" in result["sources"]
    assert "cisq" in result["sources"]
    assert len(result["principles"]) == 1
    principle = result["principles"][0]
    assert principle["name"] == "Fault Tolerance"
    assert len(principle["cwes"]) == 1
    cwe = principle["cwes"][0]
    assert cwe["id"] == 390
    assert len(cwe["refs"]) == 2
