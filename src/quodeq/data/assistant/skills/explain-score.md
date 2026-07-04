---
name: explain-score
description: Explain why a dimension scored the way it did
argument_hint: [dimension]
views: overview, violations
---
The user wants to understand a dimension's score/grade (usually the one in
`[ui-state]`). Call `get_report` for that dimension. Explain the grade from
its principles: which principles dragged it down, how many findings each has
(use `search_findings` for examples), and what improvement would move the
grade most. Lead with the answer, keep it under ~200 words.
