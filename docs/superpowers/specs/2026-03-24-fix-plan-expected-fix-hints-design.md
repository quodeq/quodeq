# Fix Plan: Per-Violation Expected Fix Hints

**Date:** 2026-03-24
**Status:** Draft

## Problem

When an AI model receives a fix plan, it knows WHAT is wrong (the violation reason) but not WHAT TO DO. This leads to:

1. **Comment-only fixes** — adding a docstring instead of extracting a helper
2. **Skipped violations** — silently dropping items it doesn't know how to fix
3. **Wrong fix type** — applying style changes when structural extraction is needed

The `reason` field describes the symptom ("function is 62 lines"). The model must infer the action ("extract a helper"). It often infers wrong.

## Solution

Add a static `**Expected fix:**` line to each violation in the generated plan markdown. The hint is derived from the violation's `req` field (requirement ID like `M-ANA-2`) via a client-side lookup table. No AI calls, no backend changes.

### Before

```markdown
### 1. Analyzability — `src/quodeq/cli.py:301`

**Why it's a violation:** Source file is 301 lines, exceeding the 300-line limit.

**Affected code:**
```

### After

```markdown
### 1. Analyzability — `src/quodeq/cli.py:301`

**Why it's a violation:** Source file is 301 lines, exceeding the 300-line limit.

**Expected fix:** Split file or extract code to a new module to reduce line count.

**Affected code:**
```

## Lookup Table Design

The table maps **requirement ID prefixes** (principle level) to fix action hints. Each dimension's principles get one entry. Individual requirement IDs (`M-ANA-1` vs `M-ANA-2`) can override the prefix default when the fix action differs within a principle.

### Matching Logic

```
1. Try exact match: FIX_HINTS[req]           (e.g., "M-ANA-1")
2. Try prefix match: FIX_HINTS[prefix]       (e.g., "M-ANA")
3. No match → skip the line (same as today)
```

### Table Entries

**Maintainability (M)**

| Req | Hint |
|-----|------|
| `M-ANA-1` | Split file or extract code to a new module to reduce line count below 300 |
| `M-ANA-2` | Extract a helper function to bring the function under 50 lines |
| `M-ANA` (fallback) | Improve code clarity — reduce nesting, add structure, simplify control flow |
| `M-MOD-1` | Reduce callees by extracting a helper that groups related calls |
| `M-MOD-4` | Group related parameters into an object or dataclass (max 5) |
| `M-MOD-5` | Extract into a configurable constant or injectable function |
| `M-MOD` (fallback) | Reduce coupling — extract dependency, use injection, or narrow the interface |
| `M-REU-1` | Extract duplicated code into a shared function or hook |
| `M-REU-2` | Add an injectable parameter so the default can be overridden for testing |
| `M-REU` (fallback) | Make the code reusable — extract shared logic or add injection points |
| `M-MDF-1` | Replace the hard-coded literal with a named constant |
| `M-MDF` (fallback) | Make the code easier to modify — extract constants, reduce coupling |
| `M-TST` | Improve testability — add injection points, reduce hidden dependencies |

**Reliability (R)**

| Req | Hint |
|-----|------|
| `R-MAT` | Add error handling, input validation, or defensive checks |
| `R-FT` | Add fault tolerance — retry logic, fallback, or graceful degradation |
| `R-REC` | Add recovery mechanism — cleanup, state restoration, or rollback |
| `R-AVL` | Improve availability — reduce single points of failure |

**Security (S)**

| Req | Hint |
|-----|------|
| `S-CON` | Fix confidentiality issue — sanitize output, restrict access, encrypt data |
| `S-INT` | Fix integrity issue — validate input, use parameterized queries, check boundaries |
| `S-AUT` | Fix authentication issue — strengthen auth checks, secure token handling |
| `S-ACC` | Fix accountability issue — add logging, audit trail, or access tracking |
| `S-NRP` | Fix non-repudiation — add tamper-evident logging or signing |

**Performance (P)**

| Req | Hint |
|-----|------|
| `P-TIM` | Optimize time behavior — reduce unnecessary computation, cache, or batch |
| `P-RES` | Reduce resource usage — close handles, limit allocations, pool connections |
| `P-CAP` | Improve capacity — add pagination, streaming, or bounded data structures |

**Flexibility (F)**

| Req | Hint |
|-----|------|
| `F-ADP` | Improve adaptability — make configurable, use abstraction, externalize settings |
| `F-SCL` | Improve scalability — avoid bottlenecks, support horizontal growth |
| `F-INS` | Improve installability — simplify setup, reduce hard-coded paths |
| `F-RPL` | Improve replaceability — use interfaces, reduce tight coupling |

**Usability (U)**

| Req | Hint |
|-----|------|
| `U-APR` | Improve recognizability — add labels, descriptions, or help text |
| `U-LRN` | Improve learnability — add examples, defaults, or progressive disclosure |
| `U-OPR` | Improve operability — simplify controls, reduce steps, add feedback |
| `U-UEP` | Add user error protection — validate input, confirm destructive actions |
| `U-UIA` | Improve aesthetics — fix layout, spacing, or visual consistency |
| `U-ACC` | Improve accessibility — add ARIA labels, keyboard nav, or contrast |

## Files Modified

### 1. `src/quodeq/ui/src/utils/explorerUtils.js`

- Add `FIX_HINTS` lookup object (exported for testing)
- Add `getFixHint(req)` function implementing the prefix match logic
- Update `renderViolationEntry()` to insert `**Expected fix:**` line after the reason

### 2. `src/quodeq/ui/src/features/explorer/components/PrincipleDetailPage.jsx`

- Update `buildPrinciplePlanText()` to include fix hint per violation
- Update `buildViolationPlanText()` to include fix hint

### 3. `src/quodeq/ui/src/features/explorer/components/EvalPrincipleDetailPage.jsx`

- Update `buildPrinciplePlanText()` to include fix hint per violation (uses `reqRefs` for req extraction)
- Update `buildViolationPlanText()` to include fix hint

### 4. `src/quodeq/ui/src/features/explorer/components/FileDetailPage.jsx`

- Update `buildFilePlanText()` to include fix hint per violation
- Update `buildViolationPlanText()` to include fix hint

### 5. `src/quodeq/ui/src/utils/explorerUtilsPlan.test.js`

- Add tests for `getFixHint()` — exact match, prefix match, no match
- Add test that dimension plan includes `Expected fix:` line when req is present
- Add test that plan omits `Expected fix:` when req is missing

## Data Flow

```
Evaluation (already done):
  AI subagent → report_finding(req="M-ANA-2", ...) → JSONL

Dashboard (already done):
  JSONL → parser → Judgment{req: "M-ANA-2"} → API → UI

Plan generation (new):
  violation.req = "M-ANA-2"
  → getFixHint("M-ANA-2")
  → exact match found: "Extract a helper function to bring the function under 50 lines"
  → rendered as **Expected fix:** line in markdown
```

## Token Cost

- **AI evaluation cost:** Zero additional — `req` already exists on every finding
- **Plan output cost:** ~10-15 words per violation. For 40 violations ≈ 500 extra tokens
- **Lookup table size:** ~40 entries, ~2KB in JS bundle — negligible

## What This Does NOT Change

- No backend changes
- No changes to the MCP tool schema
- No changes to the AI evaluator prompts
- No changes to the evidence parser
- No changes to the scoring engine
- The system preamble and operating rules stay as-is
