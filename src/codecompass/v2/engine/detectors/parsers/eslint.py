from __future__ import annotations

import json

from codecompass.v2.engine.finding import Finding

# ESLint rule → CWE mapping
_CWE_MAP: dict[str, int] = {
    "no-eval": 95,
    "no-implied-eval": 95,
    "no-new-func": 95,
    "no-explicit-any": 1121,
    "no-unused-vars": 1164,
    "@typescript-eslint/no-unused-vars": 1164,
    "no-var": 1078,
    "no-console": 1164,
    "no-debugger": 1164,
    "eqeqeq": 697,
    "no-undef": 457,
    "no-unreachable": 561,
    "no-empty-function": 1071,
    "no-shadow": 710,
    "prefer-const": 1078,
}

# ESLint severity: 2 = error, 1 = warning
_SEVERITY_MAP: dict[int, str] = {
    2: "high",
    1: "medium",
}


def parse_eslint_output(stdout: str, config: dict | None = None) -> list[Finding]:
    """Parse ESLint JSON output into Findings."""
    if not stdout or not stdout.strip():
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []

    findings: list[Finding] = []

    for file_result in data:
        filepath = file_result.get("filePath", "")
        for msg in file_result.get("messages", []):
            rule_id = msg.get("ruleId") or "unknown"
            cwe = _CWE_MAP.get(rule_id)
            severity_code = msg.get("severity", 1)
            severity = _SEVERITY_MAP.get(severity_code, "medium")

            # Map to dimension based on rule
            dimension = "maintainability"
            if rule_id in ("no-eval", "no-implied-eval", "no-new-func", "eqeqeq"):
                dimension = "security"
            elif rule_id in ("no-unreachable", "no-undef"):
                dimension = "reliability"

            findings.append(Finding(
                rule=f"eslint:{rule_id}",
                label=f"ESLint: {msg.get('message', rule_id)}",
                file=filepath,
                dimension=dimension,
                detector="tool:eslint",
                cwe=cwe,
                line=msg.get("line"),
                snippet=msg.get("source", ""),
                severity_hint=severity,
            ))

    return findings
