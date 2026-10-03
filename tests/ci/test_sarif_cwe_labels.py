"""A result's ``cwe`` property keeps the raw CWE labels; the rule's tags use the GitHub form."""
from __future__ import annotations

from quodeq.ci.sarif import build_sarif


def _doc(req_refs: list[dict]) -> dict:
    violation = {"severity": "major", "principle": "P", "req": "R-1", "file": "a.py", "line": 3,
                 "req_refs": req_refs}
    return build_sarif([{"dimension": "security", "violations": [violation]}], tool_version="1")


def test_result_cwe_labels_are_raw_undeduplicated_and_unstripped_only():
    refs = [{"label": "CWE-79"}, {"label": "cwe-79"}, {"label": " CWE-89"}, {"label": "OWASP A1"}, {}]
    doc = _doc(refs)
    assert doc["runs"][0]["results"][0]["properties"]["quodeq"]["cwe"] == ["CWE-79", "cwe-79"]


def test_rule_tags_trim_lowercase_and_deduplicate():
    refs = [{"label": "CWE-79"}, {"label": "cwe-79"}, {"label": " CWE-89"}, {"label": "OWASP A1"}]
    tags = _doc(refs)["runs"][0]["tool"]["driver"]["rules"][0]["properties"]["tags"]
    assert tags == ["quodeq", "security", "external/cwe/cwe-79", "external/cwe/cwe-89"]
