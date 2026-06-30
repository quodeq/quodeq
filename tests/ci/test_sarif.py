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
