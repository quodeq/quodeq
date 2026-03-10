import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from compile_standards import build_req_index, report_gaps, compile_dimension


def _make_iso(tmp_path, dimension, sub_chars):
    iso_file = tmp_path / "iso25010" / f"{dimension}.json"
    iso_file.parent.mkdir(parents=True, exist_ok=True)
    iso_file.write_text(json.dumps({"id": dimension, "name": dimension.title(), "sub_characteristics": sub_chars}))


def _make_cisq(tmp_path, dimension, cwes):
    cisq_file = tmp_path / "cisq" / f"{dimension}.json"
    cisq_file.parent.mkdir(parents=True, exist_ok=True)
    cisq_file.write_text(json.dumps({"cwes": cwes}))


def test_build_req_index_groups_by_principle(tmp_path):
    _make_iso(tmp_path, "reliability", [{
        "name": "Fault Tolerance",
        "requirements": [
            {"id": "R-FT-1", "text": "Exceptions MUST be handled", "cwe": [390]},
            {"id": "R-FT-2", "text": "Nulls MUST be guarded", "cwe": [476]},
        ]
    }])
    _make_cisq(tmp_path, "reliability", [])

    index = build_req_index(tmp_path, "reliability")

    assert "Fault Tolerance" in index
    reqs = index["Fault Tolerance"]
    assert len(reqs) == 2
    assert reqs[0]["id"] == "R-FT-1"
    assert reqs[0]["source"] == "iso25010"
    assert reqs[0]["text"] == "Exceptions MUST be handled"


def test_build_req_index_attaches_cwe_refs(tmp_path):
    _make_iso(tmp_path, "reliability", [{
        "name": "Fault Tolerance",
        "requirements": [{"id": "R-FT-1", "text": "Exceptions MUST be handled", "cwe": [390]}]
    }])
    _make_cisq(tmp_path, "reliability", [])

    index = build_req_index(tmp_path, "reliability")

    refs = index["Fault Tolerance"][0]["refs"]
    cwe_ref = next((r for r in refs if r["source"] == "cwe"), None)
    assert cwe_ref is not None
    assert cwe_ref["id"] == "390"
    assert cwe_ref["url"] == "https://cwe.mitre.org/data/definitions/390.html"


def test_build_req_index_attaches_cisq_refs(tmp_path):
    _make_iso(tmp_path, "maintainability", [{
        "name": "Modularity",
        "requirements": [{"id": "M-MOD-1", "text": "Complexity MUST be ≤10", "cwe": [1121]}]
    }])
    _make_cisq(tmp_path, "maintainability", [
        {"id": 1121, "name": "Excessive Complexity", "requirement": "Cyclomatic complexity MUST be ≤10"}
    ])

    index = build_req_index(tmp_path, "maintainability")

    refs = index["Modularity"][0]["refs"]
    cisq_ref = next((r for r in refs if r["source"] == "cisq"), None)
    assert cisq_ref is not None
    assert cisq_ref["name"] == "Cyclomatic complexity MUST be ≤10"
    assert cisq_ref["url"] == "https://www.it-cisq.org/coding-rules/"


def test_build_req_index_attaches_asvs_for_security(tmp_path):
    _make_iso(tmp_path, "security", [{
        "name": "Integrity",
        "requirements": [{"id": "S-INT-2", "text": "SQL MUST use parameterised statements", "cwe": [89]}]
    }])
    _make_cisq(tmp_path, "security", [{"id": 89, "name": "SQL Injection", "requirement": "Use params"}])
    asvs_file = tmp_path / "asvs" / "level1.json"
    asvs_file.parent.mkdir(parents=True, exist_ok=True)
    asvs_file.write_text(json.dumps({
        "requirements": [
            {"id": "V5.3.4", "cwe": [89], "section": "Validation",
             "text": "Verify database queries use parameterized queries"}
        ]
    }))

    index = build_req_index(tmp_path, "security")

    refs = index["Integrity"][0]["refs"]
    sources = [r["source"] for r in refs]
    assert "asvs" in sources
    asvs_ref = next(r for r in refs if r["source"] == "asvs")
    assert asvs_ref["id"] == "V5.3.4"
    assert "owasp.org" in asvs_ref["url"]


def test_build_req_index_attaches_cert_via_cwe(tmp_path):
    _make_iso(tmp_path, "reliability", [{
        "name": "Fault Tolerance",
        "requirements": [{"id": "R-FT-1", "text": "Exceptions MUST be handled", "cwe": [390]}]
    }])
    _make_cisq(tmp_path, "reliability", [])
    cert_file = tmp_path / "cert" / "reliability.json"
    cert_file.parent.mkdir(parents=True, exist_ok=True)
    cert_file.write_text(json.dumps({"rules": [
        {"id": "ERR00-J", "name": "Do not suppress checked exceptions", "cwe": [390],
         "source_url": "https://wiki.sei.cmu.edu/confluence/display/java/ERR00-J"}
    ]}))

    index = build_req_index(tmp_path, "reliability")

    refs = index["Fault Tolerance"][0]["refs"]
    cert_ref = next((r for r in refs if r["source"] == "cert"), None)
    assert cert_ref is not None
    assert cert_ref["id"] == "ERR00-J"
    assert "wiki.sei.cmu.edu" in cert_ref["url"]


def test_build_req_index_attaches_cert_via_explicit_field(tmp_path):
    _make_iso(tmp_path, "reliability", [{
        "name": "Fault Tolerance",
        "requirements": [{"id": "R-FT-2", "text": "Nulls MUST be guarded", "cwe": [476], "cert": ["ERR08-J"]}]
    }])
    _make_cisq(tmp_path, "reliability", [])
    cert_file = tmp_path / "cert" / "reliability.json"
    cert_file.parent.mkdir(parents=True, exist_ok=True)
    cert_file.write_text(json.dumps({"rules": [
        {"id": "ERR08-J", "name": "Do not catch NullPointerException", "cwe": [],
         "source_url": "https://wiki.sei.cmu.edu/confluence/display/java/ERR08-J"}
    ]}))

    index = build_req_index(tmp_path, "reliability")

    refs = index["Fault Tolerance"][0]["refs"]
    cert_ref = next((r for r in refs if r["source"] == "cert"), None)
    assert cert_ref is not None
    assert cert_ref["id"] == "ERR08-J"


def test_build_req_index_no_duplicate_cert_refs(tmp_path):
    _make_iso(tmp_path, "reliability", [{
        "name": "Recoverability",
        "requirements": [{"id": "R-REC-1", "text": "Resources MUST be closed", "cwe": [459, 772]}]
    }])
    _make_cisq(tmp_path, "reliability", [])
    cert_file = tmp_path / "cert" / "reliability.json"
    cert_file.parent.mkdir(parents=True, exist_ok=True)
    cert_file.write_text(json.dumps({"rules": [
        {"id": "FIO42-C", "name": "Close files when no longer needed", "cwe": [459, 772],
         "source_url": "https://wiki.sei.cmu.edu/confluence/display/c/FIO42-C"}
    ]}))

    index = build_req_index(tmp_path, "reliability")

    refs = index["Recoverability"][0]["refs"]
    cert_refs = [r for r in refs if r["source"] == "cert"]
    assert len(cert_refs) == 1


def test_build_req_index_attaches_wcag(tmp_path):
    _make_iso(tmp_path, "usability", [{
        "name": "Accessibility",
        "requirements": [{"id": "U-ACC-4", "text": "Images MUST have alt text", "cwe": [1059], "wcag": ["1.1.1"]}]
    }])
    wcag_file = tmp_path / "wcag" / "level_a.json"
    wcag_file.parent.mkdir(parents=True, exist_ok=True)
    wcag_file.write_text(json.dumps({"criteria": [
        {"id": "1.1.1", "name": "Non-text Content", "level": "A",
         "text": "All non-text content has a text alternative.",
         "url": "https://www.w3.org/TR/WCAG22/#non-text-content"}
    ]}))

    index = build_req_index(tmp_path, "usability")

    refs = index["Accessibility"][0]["refs"]
    wcag_ref = next((r for r in refs if r["source"] == "wcag22"), None)
    assert wcag_ref is not None
    assert wcag_ref["id"] == "1.1.1"
    assert "w3.org" in wcag_ref["url"]


def test_compile_dimension_output_shape(tmp_path):
    _make_iso(tmp_path, "reliability", [{
        "name": "Fault Tolerance",
        "requirements": [{"id": "R-FT-1", "text": "Exceptions MUST be handled", "cwe": [390]}]
    }])
    _make_cisq(tmp_path, "reliability", [
        {"id": 390, "name": "Error Without Action", "requirement": "Errors MUST trigger handling"}
    ])

    result = compile_dimension(tmp_path, "reliability")

    assert result["id"] == "reliability"
    assert "iso25010" in result["sources"]
    assert "cisq" in result["sources"]
    assert len(result["principles"]) == 1

    principle = result["principles"][0]
    assert principle["name"] == "Fault Tolerance"
    assert principle["source"] == "iso25010"
    assert "requirements" in principle
    assert "cwes" not in principle

    req = principle["requirements"][0]
    assert req["id"] == "R-FT-1"
    assert req["source"] == "iso25010"
    assert req["text"] == "Exceptions MUST be handled"
    assert "severity" in req
    assert "scope" in req
    assert "_cwe_ids" not in req

    sources = [r["source"] for r in req["refs"]]
    assert "cwe" in sources
    assert "cisq" in sources


def test_compile_dimension_severity_scope_passed_through(tmp_path):
    _make_iso(tmp_path, "reliability", [{
        "name": "Fault Tolerance",
        "requirements": [
            {"id": "R-FT-1", "text": "...", "cwe": [390], "severity": "high", "scope": "api"}
        ]
    }])
    _make_cisq(tmp_path, "reliability", [])

    result = compile_dimension(tmp_path, "reliability")
    req = result["principles"][0]["requirements"][0]
    assert req["severity"] == "high"
    assert req["scope"] == "api"


def test_report_gaps_finds_orphan_cwes(tmp_path):
    _make_iso(tmp_path, "maintainability", [{
        "name": "Modularity",
        "requirements": [{"id": "M-MOD-1", "text": "...", "cwe": [1121]}]
    }])
    _make_cisq(tmp_path, "maintainability", [
        {"id": 1121, "name": "Complexity", "requirement": "..."},
        {"id": 9999, "name": "Orphan CWE", "requirement": "..."}
    ])

    gaps = report_gaps(tmp_path, "maintainability")
    assert len(gaps) == 1
    assert "9999" in gaps[0]
    assert "Orphan CWE" in gaps[0]
