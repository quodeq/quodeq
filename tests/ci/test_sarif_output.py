"""SARIF export: path safety, official schema validation and the golden document."""
import json as _json
from pathlib import Path

import pytest

from quodeq.ci.sarif import build_sarif

from tests.ci._sarif_helpers import _report, _violation


def test_no_absolute_paths_or_project_field_anywhere():
    report = _report(
        "reliability",
        [_violation(file="src/api/x.py")],
        project="/Users/victor/GitHub/secret-project",
        runId="abc123",
    )
    doc = build_sarif([report], tool_version="1.4.0", include_snippets=True)
    blob = _json.dumps(doc)
    assert "/Users/" not in blob
    assert "secret-project" not in blob
    assert "abc123" not in blob
    # Every uri is relative POSIX.
    for run in doc["runs"]:
        for result in run["results"]:
            for loc in result.get("locations", []):
                uri = loc["physicalLocation"]["artifactLocation"]["uri"]
                assert not uri.startswith("/")
                assert "\\" not in uri


def test_windows_style_path_is_relativized():
    doc = build_sarif(
        [_report("reliability", [_violation(file="src\\api\\x.py")])],
        tool_version="1.4.0",
    )
    uri = doc["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "src/api/x.py"



_SCHEMA_PATH = Path(__file__).parent / "fixtures" / "sarif-schema-2.1.0.json"


@pytest.mark.skipif(not _SCHEMA_PATH.exists(), reason="SARIF schema fixture not vendored")
def test_build_sarif_validates_against_official_schema():
    import json
    import jsonschema

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    doc = build_sarif(
        [
            _report("reliability", [_violation()]),
            _report("security", [_violation(principle="Authentication", req="S-AUT-1", severity="critical")]),
        ],
        tool_version="1.4.0",
        include_snippets=True,
    )
    # Use Draft202012Validator directly to match the schema's declared $schema
    # and avoid jsonschema.validate calling check_schema(), which rejects a
    # regex in the SARIF schema itself on Python 3.14+.
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(doc))
    assert errors == [], "\n".join(str(e) for e in errors)


@pytest.mark.skipif(not _SCHEMA_PATH.exists(), reason="SARIF schema fixture not vendored")
def test_empty_sarif_validates_against_official_schema():
    import json
    import jsonschema

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    doc = build_sarif([_report("reliability", [])], tool_version="1.4.0")
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(doc))
    assert errors == [], "\n".join(str(e) for e in errors)


def test_golden_two_findings():
    reports = [
        _report("reliability", [
            _violation(file="app.py", line=58, end_line=59, severity="major",
                       title="Empty except", reason="Bare except hides failures.", req="R-FT-1",
                       req_refs=[{"label": "CWE-390", "url": "https://cwe.mitre.org/data/definitions/390.html"}],
                       snippet="except:\n    pass"),
        ]),
        _report("security", [
            _violation(principle="Authentication", file="auth.py", line=5, end_line=5, severity="critical",
                       title="Hardcoded creds", reason="Credentials in source.", req="S-AUT-1",
                       req_refs=[{"label": "CWE-798", "url": "https://cwe.mitre.org/data/definitions/798.html"}],
                       snippet="PASS = 'admin'"),
        ]),
    ]
    doc = build_sarif(reports, tool_version="1.4.0")

    run = doc["runs"][0]
    # Rules sorted by id; two distinct (dimension, principle).
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == [
        "reliability/fault-tolerance",
        "security/authentication",
    ]
    # Results sorted by (uri, startLine, ruleId).
    assert [r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in run["results"]] == [
        "app.py",
        "auth.py",
    ]
    # Security rule has worst-of critical security-severity and the CWE tag.
    sec_rule = next(r for r in run["tool"]["driver"]["rules"] if r["id"] == "security/authentication")
    assert sec_rule["properties"]["security-severity"] == "9.0"
    assert "external/cwe/cwe-798" in sec_rule["properties"]["tags"]
    # Snippets omitted by default.
    region = run["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert "snippet" not in region
