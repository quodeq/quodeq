# Finding Dismissal & False-Positive Prevention

**Date:** 2026-04-01
**Status:** Approved

## Problem

The AI evaluation pipeline produces false positives — findings that are technically correct pattern matches but don't represent real issues (e.g., "magic strings" that exist only inside a named constant definition). These inflate violation counts and drag grades down unfairly. Users have no way to exclude them.

## Solution

Two complementary features:

1. **Counter-argument step in verification** — Prompt-level change that asks the AI to check for common false-positive patterns before confirming a finding
2. **Finding dismissal mechanism** — Lets users permanently dismiss individual findings, excluding them from scoring, with a UI to view and restore dismissed findings

## Feature A: Counter-Argument in Verification Prompt

### What changes

Add a false-positive check clause to `_VERIFY_PROMPT_TEMPLATE` in `src/quodeq/analysis/subagents/_verify_pool.py`.

After step 3 ("check if the violation/compliance condition still applies"), insert:

> 4. Before confirming, check for false positives. Common patterns:
>    - String/number literal inside a constant, enum, or config definition is NOT a "magic literal" violation — the definition IS the fix
>    - A long function that only registers routes/handlers with no extractable logic is not always splittable
>    - Duplicated code in test fixtures may be intentional for test clarity
>    - If the finding targets the fix itself, skip it

### Scope

- One file changed: `_verify_pool.py`
- No code changes beyond the prompt string
- Also applies during initial analysis via the subagent prompt (`subagent.md`) — add a similar note in the Rules section

## Feature B: Finding Dismissal

### Storage

Dismissed findings stored at:
```
~/.quodeq/evaluations/<project>/dismissed.json
```

Project-level file (not per-run, not per-dimension) so dismissals persist across evaluations.

Schema:
```json
[
  {
    "req": "M-MOD-4",
    "file": "useStandards.js",
    "line": 4,
    "dimension": "maintainability",
    "severity": "minor",
    "reason": "String literals inside STANDARD_TYPES constant definition",
    "dismissed_at": "2026-04-01T12:00:00Z"
  }
]
```

**Finding identity:** A dismissed finding matches by `(req, file, line)` tuple. If the same requirement is violated at the same file and line, it's considered the same finding.

### Backend API

Three endpoints on the existing Flask app:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/findings/dismissed?project=<id>` | List dismissed findings for a project |
| `POST` | `/api/findings/dismiss` | Dismiss a finding (body: `{ project, req, file, line, dimension, severity, reason }`) |
| `POST` | `/api/findings/restore` | Restore a finding (body: `{ project, req, file, line }`) |

Implementation:
- New file: `src/quodeq/api/routes_findings.py` — registers the three routes
- Storage helper: `src/quodeq/services/dismissed.py` — read/write/remove from `dismissed.json`
- Register routes in the existing app factory

### Verification Integration

In `src/quodeq/analysis/subagents/verify.py`, `load_previous_findings_for_dimension`:
- After loading previous findings, load the project's `dismissed.json`
- Filter out any finding whose `(req, file, line)` matches a dismissed entry
- Dismissed findings are not sent to verification subagents and not carried forward

### Scoring Integration

In `src/quodeq/services/violations_parsing.py`, `_parse_jsonl_findings`:
- Accept an optional `dismissed_keys: set[tuple] | None` parameter
- Skip any parsed finding whose `(req, file, line)` is in the dismissed set
- The caller (`resolve_dimension_eval` or its chain) loads dismissed findings and passes the set

### UI: Dismiss Button on Violation Cards

In `src/quodeq/ui/src/features/explorer/components/EvalCards.jsx`:
- Add a "Dismiss" button to `EvalViolationCard`, next to "Fix plan"
- Small, unobtrusive — same style as "Fix plan" button
- On click: calls `POST /api/findings/dismiss` with the finding's data
- Card animates out (fade + slide left, 300ms)
- Parent component removes it from the active violations list

### UI: Dismissed Section in Violations Tab

In `src/quodeq/ui/src/features/violations/components/ViolationsPage.jsx`:
- At the bottom of the page, add a collapsible "Dismissed findings (N)" bar
- Collapsed by default — shows count badge and "Not included in scoring" note
- When expanded, shows dismissed cards in a compact format:
  - Greyed out (opacity 0.55, 0.8 on hover)
  - Each card shows: dismissed tag, principle label, file ref, reason
  - "Restore" button on each card
- On restore: calls `POST /api/findings/restore`, removes from dismissed list, finding reappears in next evaluation or page refresh

### UI: API Client

In `src/quodeq/ui/src/api/index.js`, add:
- `dismissFinding(project, finding)` — POST to dismiss endpoint
- `restoreFinding(project, finding)` — POST to restore endpoint
- `listDismissedFindings(project)` — GET dismissed for project

### Data Flow

```
User clicks Dismiss on violation card
  → POST /api/findings/dismiss
  → Server appends to dismissed.json
  → Card removed from UI

Next evaluation runs
  → Verification loads dismissed.json
  → Skips matching findings
  → Scoring excludes dismissed findings
  → Grade reflects only active findings

User opens Violations tab
  → Page loads dismissed list
  → Shows in collapsed section at bottom
  → User can Restore → POST /api/findings/restore → removed from dismissed.json
```

## Files Changed

### Feature A (prompt)
- `src/quodeq/analysis/subagents/_verify_pool.py` — add false-positive clause to verification prompt
- `src/quodeq/data/prompts/subagent.md` — add false-positive note in Rules section

### Feature B (dismissal)
- `src/quodeq/api/routes_findings.py` — new file, 3 routes
- `src/quodeq/services/dismissed.py` — new file, read/write/remove helpers
- `src/quodeq/api/routes.py` — register new routes in app factory (or wherever routes are registered)
- `src/quodeq/analysis/subagents/verify.py` — filter dismissed in `load_previous_findings_for_dimension`
- `src/quodeq/services/violations_parsing.py` — accept dismissed_keys param in `_parse_jsonl_findings`
- `src/quodeq/services/violations.py` — pass dismissed set through the chain
- `src/quodeq/ui/src/api/index.js` — add 3 API functions
- `src/quodeq/ui/src/features/explorer/components/EvalCards.jsx` — dismiss button on violation card
- `src/quodeq/ui/src/features/violations/components/ViolationsPage.jsx` — dismissed section
- `src/quodeq/ui/src/styles/evaluation.css` — dismissed card styles

### Tests
- `tests/services/test_dismissed.py` — new, test read/write/remove
- `tests/api/test_routes_findings.py` — new, test 3 endpoints
- `tests/engine/test_verification_dismissed.py` — test filtering in verify.py
