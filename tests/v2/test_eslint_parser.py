from __future__ import annotations

import json

from codecompass.v2.engine.detectors.parsers.eslint import parse_eslint_output


def test_empty_output():
    assert parse_eslint_output("") == []
    assert parse_eslint_output("   ") == []


def test_invalid_json():
    assert parse_eslint_output("not json") == []


def test_single_file_parsing():
    data = [{
        "filePath": "/src/app.ts",
        "messages": [
            {"ruleId": "no-eval", "severity": 2, "message": "eval is evil", "line": 10, "source": "eval(x)"},
            {"ruleId": "no-unused-vars", "severity": 1, "message": "unused var", "line": 5, "source": "let x;"},
        ],
        "errorCount": 1,
        "warningCount": 1,
    }]
    findings = parse_eslint_output(json.dumps(data))
    assert len(findings) == 2
    assert findings[0].rule == "eslint:no-eval"
    assert findings[0].dimension == "security"
    assert findings[0].line == 10
    assert findings[1].rule == "eslint:no-unused-vars"


def test_cwe_mapping():
    data = [{
        "filePath": "/src/app.ts",
        "messages": [
            {"ruleId": "no-eval", "severity": 2, "message": "eval"},
        ],
    }]
    findings = parse_eslint_output(json.dumps(data))
    assert findings[0].cwe == 95


def test_severity_mapping():
    data = [{
        "filePath": "/src/app.ts",
        "messages": [
            {"ruleId": "no-eval", "severity": 2, "message": "error"},
            {"ruleId": "no-var", "severity": 1, "message": "warning"},
        ],
    }]
    findings = parse_eslint_output(json.dumps(data))
    assert findings[0].severity_hint == "high"
    assert findings[1].severity_hint == "medium"


def test_unknown_rule():
    data = [{
        "filePath": "/src/app.ts",
        "messages": [
            {"ruleId": "custom/my-rule", "severity": 1, "message": "custom"},
        ],
    }]
    findings = parse_eslint_output(json.dumps(data))
    assert len(findings) == 1
    assert findings[0].cwe is None
    assert findings[0].dimension == "maintainability"
