---
name: explain-finding
description: Explain a finding in depth, with code context
argument_hint: [file:line or search terms]
views: violations
---
The user wants to understand one finding (usually the one selected in
`[ui-state]`). Use `search_findings` to fetch it, then `read_repo_file` on the
finding's file to see the code around the reported line. Explain: what the
issue is, why quodeq flagged it against the requirement, the risk in this
specific code, and a concrete fix sketch. Quote at most a few lines of code.
