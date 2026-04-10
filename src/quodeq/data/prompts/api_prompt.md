Analyze the following source code for the "{{DIMENSION}}" quality dimension.

Repository: {{REPO_NAME}}

## Standards Checklist (JSON)

The checklist below is a JSON array. Each element is a principle group with its requirements.
You MUST evaluate EVERY principle group — not just the first ones.

{{STANDARDS_TEXT}}

## Source Files

{{FILES_BLOCK}}

## Your Task

Evaluate the source files against EACH principle group in the checklist above.

{{EVALUATION_RULES}}

{{FINDING_SCHEMA}}

Respond with ONLY this JSON format — no other text:
{"findings": [{"req": "M-MOD-1", "t": "violation", "file": "src/app.py", "line": 10, "severity": "major", "w": "Multiple responsibilities", "reason": "Module handles both IO and logic"}]}

If no issues found: {"findings": []}
