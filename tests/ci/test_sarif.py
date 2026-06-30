from quodeq.ci.sarif import (
    _severity_level,
    _security_severity,
    _severity_rank,
    _slug,
    _rule_id,
)


def test_severity_level_maps_canonical_severities():
    assert _severity_level("critical") == "error"
    assert _severity_level("major") == "error"
    assert _severity_level("high") == "error"
    assert _severity_level("minor") == "warning"
    assert _severity_level("unknown") == "note"
    assert _severity_level("") == "note"
    assert _severity_level("weird") == "note"


def test_security_severity_is_string_decimal():
    assert _security_severity("critical") == "9.0"
    assert _security_severity("major") == "7.0"
    assert _security_severity("minor") == "4.0"
    assert _security_severity("unknown") == "2.0"


def test_severity_rank_orders_high_to_low():
    assert _severity_rank("critical") > _severity_rank("major")
    assert _severity_rank("major") > _severity_rank("minor")
    assert _severity_rank("minor") > _severity_rank("unknown")
    assert _severity_rank("nonsense") == _severity_rank("unknown")


def test_slug_lowercases_and_hyphenates():
    assert _slug("Fault Tolerance") == "fault-tolerance"
    assert _slug("  Spaced  Out  ") == "spaced-out"
    assert _slug("Mixed/Case & Symbols!") == "mixed-case-symbols"


def test_rule_id_joins_dimension_and_principle_slug():
    assert _rule_id("reliability", "Fault Tolerance") == "reliability/fault-tolerance"


from quodeq.ci.sarif import _cwe_tags, _safe_uri


def test_cwe_tags_extracts_github_form_from_req_refs():
    refs = [
        {"label": "CWE-390", "url": "https://cwe.mitre.org/data/definitions/390.html"},
        {"label": "CISQ", "url": "https://www.it-cisq.org/"},
        {"label": "cwe-79", "url": ""},
    ]
    assert _cwe_tags(refs) == ["external/cwe/cwe-390", "external/cwe/cwe-79"]


def test_cwe_tags_handles_missing_or_empty():
    assert _cwe_tags(None) == []
    assert _cwe_tags([]) == []
    assert _cwe_tags([{"label": "CISQ"}]) == []


def test_safe_uri_normalizes_to_relative_posix():
    assert _safe_uri("app.py") == "app.py"
    assert _safe_uri("src/api/x.py") == "src/api/x.py"
    assert _safe_uri("src\\api\\x.py") == "src/api/x.py"
    assert _safe_uri("/abs/leak.py") == "abs/leak.py"  # leading slash stripped


def test_safe_uri_rejects_blank_and_escaping():
    assert _safe_uri("") is None
    assert _safe_uri(None) is None
    assert _safe_uri("../outside.py") is None
    assert _safe_uri("a/../../b.py") is None


from quodeq.ci.sarif import build_sarif


def _report(dimension, violations, **extra):
    return {"dimension": dimension, "violations": violations, "compliance": [], **extra}


def _violation(**kw):
    base = {
        "principle": "Fault Tolerance",
        "file": "app.py",
        "line": 58,
        "end_line": 59,
        "title": "Empty except swallows errors",
        "reason": "The bare except hides failures.",
        "snippet": "except:\n    pass",
        "severity": "major",
        "req": "R-FT-1",
        "req_refs": [{"label": "CWE-390", "url": "https://cwe.mitre.org/data/definitions/390.html"}],
    }
    base.update(kw)
    return base


def test_build_sarif_top_level_shape():
    doc = build_sarif([_report("reliability", [_violation()])], tool_version="1.4.0")
    assert doc["version"] == "2.1.0"
    assert doc["$schema"].endswith("sarif-2.1.0.json")
    assert len(doc["runs"]) == 1
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "Quodeq"
    assert run["tool"]["driver"]["version"] == "1.4.0"
    assert run["automationDetails"]["id"] == "quodeq/scan"


def test_build_sarif_result_fields():
    doc = build_sarif([_report("reliability", [_violation()])], tool_version="1.4.0")
    result = doc["runs"][0]["results"][0]
    assert result["ruleId"] == "reliability/fault-tolerance"
    assert result["level"] == "error"
    assert result["message"]["text"]
    loc = result["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "app.py"
    assert loc["region"]["startLine"] == 58
    assert loc["region"]["endLine"] == 59
    assert result["partialFingerprints"]["quodeqReqSnippet/v1"]
    assert result["properties"]["quodeq"]["req"] == "R-FT-1"


def test_build_sarif_rule_carries_cwe_and_security_severity():
    doc = build_sarif([_report("reliability", [_violation()])], tool_version="1.4.0")
    rules = doc["runs"][0]["tool"]["driver"]["rules"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["id"] == "reliability/fault-tolerance"
    assert rule["properties"]["security-severity"] == "7.0"
    assert "security" in rule["properties"]["tags"]
    assert "external/cwe/cwe-390" in rule["properties"]["tags"]


def test_build_sarif_worst_severity_drives_rule_security_severity():
    violations = [
        _violation(severity="minor", title="minor one", snippet="a"),
        _violation(severity="critical", title="crit one", snippet="b"),
    ]
    doc = build_sarif([_report("reliability", violations)], tool_version="1.4.0")
    rule = doc["runs"][0]["tool"]["driver"]["rules"][0]
    assert rule["properties"]["security-severity"] == "9.0"  # worst = critical


def test_build_sarif_merges_dimensions_into_one_run():
    doc = build_sarif(
        [
            _report("reliability", [_violation()]),
            _report("security", [_violation(principle="Authentication", req="S-AUT-1")]),
        ],
        tool_version="1.4.0",
    )
    assert len(doc["runs"]) == 1
    rule_ids = {r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]}
    assert rule_ids == {"reliability/fault-tolerance", "security/authentication"}


def test_build_sarif_excludes_compliance_and_dismissed():
    rep = _report("reliability", [_violation(verdict="violation")])
    rep["compliance"] = [{"principle": "X", "file": "y.py"}]
    doc = build_sarif([rep], tool_version="1.4.0")
    assert len(doc["runs"][0]["results"]) == 1


def test_build_sarif_empty_when_no_violations():
    doc = build_sarif([_report("reliability", [])], tool_version="1.4.0")
    assert doc["runs"][0]["results"] == []
    assert doc["runs"][0]["tool"]["driver"]["rules"] == []


def test_build_sarif_is_deterministic():
    reports = [
        _report("security", [_violation(principle="Authentication", req="S-AUT-1", file="b.py")]),
        _report("reliability", [_violation(file="a.py")]),
    ]
    import json
    assert json.dumps(build_sarif(reports, tool_version="1.4.0")) == json.dumps(
        build_sarif(reports, tool_version="1.4.0")
    )


def test_build_sarif_clamps_startline_and_tolerates_missing_fields():
    v = _violation(line=0, end_line=None, file=None, req=None, req_refs=None, snippet=None)
    doc = build_sarif([_report("reliability", [v])], tool_version="1.4.0")
    result = doc["runs"][0]["results"][0]
    # No usable file -> no locations, but the result still exists with a message.
    assert result.get("locations", []) == []
    assert result["message"]["text"]
    assert "partialFingerprints" not in result  # req and snippet both blank


def test_min_severity_filters_below_threshold():
    violations = [
        _violation(severity="critical", title="c", snippet="c"),
        _violation(severity="major", title="m", snippet="m"),
        _violation(severity="minor", title="n", snippet="n"),
        _violation(severity="unknown", title="u", snippet="u"),
    ]
    reports = [_report("reliability", violations)]

    all_doc = build_sarif(reports, tool_version="1.4.0")
    assert len(all_doc["runs"][0]["results"]) == 4

    major_doc = build_sarif(reports, tool_version="1.4.0", min_severity="major")
    levels = [r["properties"]["quodeq"]["severity"] for r in major_doc["runs"][0]["results"]]
    assert sorted(levels) == ["critical", "major"]

    minor_doc = build_sarif(reports, tool_version="1.4.0", min_severity="minor")
    assert len(minor_doc["runs"][0]["results"]) == 3  # drops unknown


def test_with_snippets_toggles_snippet_text():
    reports = [_report("reliability", [_violation(snippet="secret = 'x'")])]

    off = build_sarif(reports, tool_version="1.4.0", include_snippets=False)
    region_off = off["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert "snippet" not in region_off

    on = build_sarif(reports, tool_version="1.4.0", include_snippets=True)
    region_on = on["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert region_on["snippet"]["text"] == "secret = 'x'"
