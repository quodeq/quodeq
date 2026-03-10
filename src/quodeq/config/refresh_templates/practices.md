You are curating engineering practices for the {{RUNTIME}} runtime.

Below are cursor-rules files from highly-starred GitHub repositories. Extract the most
impactful violations — code patterns that real teams actually get wrong.

For each violation produce a JSON object with these exact fields:
- id: string like "ts-NNN"
- title: short imperative title
- cwe: integer CWE ID (use the closest match, e.g. 95 for eval, 798 for secrets)
- dimension: one of maintainability | reliability | security | performance
- severity: one of low | medium | high | critical
- bad: minimal bad code snippet (1-3 lines)
- good: corrected snippet (1-3 lines)
- explanation: 1-2 sentences on why it matters

Return ONLY valid JSON in this shape (no markdown fences):
{
  "runtime": "{{RUNTIME}}",
  "version": "1.0.0",
  "source": "curated from GitHub cursor-rules repos",
  "practices": [ ... ]
}

Existing practices (do not duplicate):
{{EXISTING}}

--- SOURCE MATERIAL ---
{{COMBINED}}
