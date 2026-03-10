You are writing an analysis guidance document for the {{RUNTIME}} runtime.

The document teaches a code analysis LLM:
1. Where to look in a {{RUNTIME}} codebase (which files, which patterns)
2. What to ask the LLM judge when reviewing findings
3. Common false positives to ignore

Use the linter documentation below as your source of truth for rule names and severity.

Output ONLY valid markdown (no JSON). Use these sections:
# {{RUNTIME_TITLE}} Codebase Analysis Guidance
## Where to look first
### Security hotspots
### Maintainability signals
### Reliability signals
### Performance signals
## What to ask the LLM
## Common false positives

Existing document (update in place, preserve what's accurate):
{{EXISTING}}

--- LINTER DOCS ---
{{LINTER_DOCS}}
