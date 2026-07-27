---
name: verify-finding
description: Adversarially verify a finding, then dismiss it or mark it verified
argument_hint: [file:line or search terms]
requires_write: true
---
The user wants to know whether one finding (usually the one selected in
`[ui-state]`) is a real defect or a false positive. Work in this order:
1. Locate the finding: `search_findings` when a run is selected, otherwise
   `get_violations` for the dimension in `[ui-state]`.
2. Read the requirement text with `get_standard` so you judge against what the
   standard actually demands, not the finding's own summary.
3. Read the cited code with `read_repo_file`, plus any related file (imports,
   callers) when the verdict hinges on behavior elsewhere.
4. Argue adversarially: try to refute the finding before accepting it. State
   REAL or FALSE POSITIVE with a confidence (high, medium, low) and the
   decisive evidence.
5. Draft exactly one action with `draft_action`. The payload's `req`, `file`
   and `line` must be copied verbatim from the finding you located in step 1
   (`req` may be empty when the finding has none); made-up keys are rejected.
   FALSE POSITIVE -> `action_type: "dismiss_finding"`, payload
   `{req, file, line, reason}` with your reasoning as the reason.
   REAL -> `action_type: "verify_finding"`, payload `{req, file, line, note}`
   with a one-line note. The user approves or rejects the card;
   never claim the action was applied.
Keep the reply under ~250 words and quote at most a few lines of code.
