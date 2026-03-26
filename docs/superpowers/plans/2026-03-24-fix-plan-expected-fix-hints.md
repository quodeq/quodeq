# Fix Plan Expected Fix Hints — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-violation `Expected fix:` hints and a completion checklist to fix plan markdown, so AI models know exactly what action to take and can't silently skip violations.

**Architecture:** A static lookup table in `explorerUtils.js` maps requirement IDs (e.g., `M-ANA-2`) to fix action strings. The `getFixHint()` function does exact-then-prefix matching. All plan builders call it when rendering violations. A `PLAN_COMPLETION_CHECKLIST` constant is appended to every group plan.

**Tech Stack:** JavaScript (React UI), Node.js test runner

---

### Task 1: Add FIX_HINTS lookup and getFixHint() to explorerUtils.js

**Files:**
- Modify: `src/quodeq/ui/src/utils/explorerUtils.js`
- Test: `src/quodeq/ui/src/utils/explorerUtilsPlan.test.js`

- [ ] **Step 1: Write failing tests for getFixHint()**

Add to the end of `explorerUtilsPlan.test.js`:

```js
import {
  PLAN_TEST_INSTRUCTION_GROUP,
  buildDimensionPlanText,
  buildDimensionPlanFromViolations,
  getFixHint,
  PLAN_COMPLETION_CHECKLIST,
} from './explorerUtils.js';

// ---------------------------------------------------------------------------
// getFixHint
// ---------------------------------------------------------------------------

test('getFixHint returns exact match for specific req ID', () => {
  assert.equal(getFixHint('M-ANA-1'), 'Split file or extract code to a new module to reduce line count below 300');
});

test('getFixHint returns exact match for M-ANA-2', () => {
  assert.equal(getFixHint('M-ANA-2'), 'Extract a helper function to bring the function under 50 lines');
});

test('getFixHint falls back to prefix match', () => {
  // M-ANA-7 has no exact match, should match M-ANA prefix
  const hint = getFixHint('M-ANA-7');
  assert.ok(hint, 'should return a fallback hint');
  assert.ok(hint.includes('clarity'), 'should be the M-ANA fallback');
});

test('getFixHint returns null for unknown req', () => {
  assert.equal(getFixHint('X-ZZZ-99'), null);
});

test('getFixHint returns null for empty/null req', () => {
  assert.equal(getFixHint(null), null);
  assert.equal(getFixHint(''), null);
  assert.equal(getFixHint(undefined), null);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/quodeq/ui && node --test src/utils/explorerUtilsPlan.test.js`
Expected: FAIL — `getFixHint` is not exported

- [ ] **Step 3: Add FIX_HINTS table and getFixHint() to explorerUtils.js**

Add after `PLAN_TEST_INSTRUCTION_SINGLE` (around line 7), before `PLAN_SYSTEM_PREAMBLE`:

```js
export const FIX_HINTS = {
  // Maintainability
  'M-ANA-1': 'Split file or extract code to a new module to reduce line count below 300',
  'M-ANA-2': 'Extract a helper function to bring the function under 50 lines',
  'M-ANA':   'Improve code clarity — reduce nesting, add structure, simplify control flow',
  'M-MOD-1': 'Reduce callees by extracting a helper that groups related calls',
  'M-MOD-4': 'Group related parameters into an object or dataclass (max 5)',
  'M-MOD-5': 'Extract into a configurable constant or injectable function',
  'M-MOD':   'Reduce coupling — extract dependency, use injection, or narrow the interface',
  'M-REU-1': 'Extract duplicated code into a shared function or hook',
  'M-REU-2': 'Add an injectable parameter so the default can be overridden for testing',
  'M-REU':   'Make the code reusable — extract shared logic or add injection points',
  'M-MDF-1': 'Replace the hard-coded literal with a named constant',
  'M-MDF':   'Make the code easier to modify — extract constants, reduce coupling',
  'M-TST':   'Improve testability — add injection points, reduce hidden dependencies',
  // Reliability
  'R-MAT':   'Add error handling, input validation, or defensive checks',
  'R-FT':    'Add fault tolerance — retry logic, fallback, or graceful degradation',
  'R-REC':   'Add recovery mechanism — cleanup, state restoration, or rollback',
  'R-AVL':   'Improve availability — reduce single points of failure',
  // Security
  'S-CON':   'Fix confidentiality issue — sanitize output, restrict access, encrypt data',
  'S-INT':   'Fix integrity issue — validate input, use parameterized queries, check boundaries',
  'S-AUT':   'Fix authentication issue — strengthen auth checks, secure token handling',
  'S-ACC':   'Fix accountability issue — add logging, audit trail, or access tracking',
  'S-NRP':   'Fix non-repudiation — add tamper-evident logging or signing',
  // Performance
  'P-TIM':   'Optimize time behavior — reduce unnecessary computation, cache, or batch',
  'P-RES':   'Reduce resource usage — close handles, limit allocations, pool connections',
  'P-CAP':   'Improve capacity — add pagination, streaming, or bounded data structures',
  // Flexibility
  'F-ADP':   'Improve adaptability — make configurable, use abstraction, externalize settings',
  'F-SCL':   'Improve scalability — avoid bottlenecks, support horizontal growth',
  'F-INS':   'Improve installability — simplify setup, reduce hard-coded paths',
  'F-RPL':   'Improve replaceability — use interfaces, reduce tight coupling',
  // Usability
  'U-APR':   'Improve recognizability — add labels, descriptions, or help text',
  'U-LRN':   'Improve learnability — add examples, defaults, or progressive disclosure',
  'U-OPR':   'Improve operability — simplify controls, reduce steps, add feedback',
  'U-UEP':   'Add user error protection — validate input, confirm destructive actions',
  'U-UIA':   'Improve aesthetics — fix layout, spacing, or visual consistency',
  'U-ACC':   'Improve accessibility — add ARIA labels, keyboard nav, or contrast',
};

/**
 * Look up a fix hint for a requirement ID.
 * Tries exact match first, then prefix (e.g., "M-ANA" from "M-ANA-7").
 * Returns null if no match.
 */
export function getFixHint(req) {
  if (!req) return null;
  if (FIX_HINTS[req]) return FIX_HINTS[req];
  const prefix = req.replace(/-\d+$/, '');
  return FIX_HINTS[prefix] || null;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/quodeq/ui && node --test src/utils/explorerUtilsPlan.test.js`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/ui/src/utils/explorerUtils.js src/quodeq/ui/src/utils/explorerUtilsPlan.test.js
git commit -m "feat: add FIX_HINTS lookup table and getFixHint() for fix plans"
```

---

### Task 2: Add PLAN_COMPLETION_CHECKLIST constant

**Files:**
- Modify: `src/quodeq/ui/src/utils/explorerUtils.js`
- Test: `src/quodeq/ui/src/utils/explorerUtilsPlan.test.js`

- [ ] **Step 1: Write failing test**

Add to `explorerUtilsPlan.test.js`:

```js
test('PLAN_COMPLETION_CHECKLIST contains key enforcement phrases', () => {
  assert.ok(PLAN_COMPLETION_CHECKLIST.includes('Every violation has a code change'));
  assert.ok(PLAN_COMPLETION_CHECKLIST.includes('No violations were skipped'));
  assert.ok(PLAN_COMPLETION_CHECKLIST.includes('Tests pass'));
  assert.ok(PLAN_COMPLETION_CHECKLIST.includes('Verify metrics'));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd src/quodeq/ui && node --test src/utils/explorerUtilsPlan.test.js`
Expected: FAIL — `PLAN_COMPLETION_CHECKLIST` is not exported

- [ ] **Step 3: Add PLAN_COMPLETION_CHECKLIST to explorerUtils.js**

Add after `PLAN_TEST_INSTRUCTION_SINGLE`:

```js
export const PLAN_COMPLETION_CHECKLIST = [
  '---', '',
  '## Completion checklist', '',
  'Before claiming this plan is done, verify:', '',
  '- [ ] **Every violation has a code change.** Count your diffs — the number must match the total violations above. A comment or docstring is NOT a fix unless the violation specifically requires documentation.',
  '- [ ] **No violations were skipped.** If a violation cannot be fixed, state why explicitly — do not silently omit it.',
  '- [ ] **Tests pass.** Run the full test suite after all changes.',
  '- [ ] **Verify metrics.** For each function-length or file-length violation, confirm the result is within limits (e.g., `wc -l`, AST line count).',
].join('\n');
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd src/quodeq/ui && node --test src/utils/explorerUtilsPlan.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/ui/src/utils/explorerUtils.js src/quodeq/ui/src/utils/explorerUtilsPlan.test.js
git commit -m "feat: add PLAN_COMPLETION_CHECKLIST constant"
```

---

### Task 3: Wire hints and checklist into dimension plans (explorerUtils.js)

**Files:**
- Modify: `src/quodeq/ui/src/utils/explorerUtils.js`
- Test: `src/quodeq/ui/src/utils/explorerUtilsPlan.test.js`

- [ ] **Step 1: Write failing tests**

Add to `explorerUtilsPlan.test.js`:

```js
test('dimension plan includes Expected fix line when violation has req', () => {
  const violations = [
    { severity: 'major', file: 'a.py', principle: 'Analyzability', reason: 'Too long', req: 'M-ANA-2' },
  ];
  const result = buildDimensionPlanFromViolations('Maintainability', violations);
  assert.ok(result.includes('**Expected fix:**'), 'should contain Expected fix line');
  assert.ok(result.includes('Extract a helper function'), 'should contain the M-ANA-2 hint');
});

test('dimension plan omits Expected fix line when violation has no req', () => {
  const violations = [
    { severity: 'major', file: 'a.py', principle: 'Analyzability', reason: 'Too long' },
  ];
  const result = buildDimensionPlanFromViolations('Maintainability', violations);
  assert.ok(!result.includes('**Expected fix:**'), 'should not contain Expected fix line');
});

test('dimension plan includes completion checklist', () => {
  const violations = [
    { severity: 'minor', file: 'a.py', principle: 'X', reason: 'Y' },
  ];
  const result = buildDimensionPlanFromViolations('Test', violations);
  assert.ok(result.includes('## Completion checklist'), 'should contain checklist');
  assert.ok(result.includes('Every violation has a code change'), 'should contain enforcement');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd src/quodeq/ui && node --test src/utils/explorerUtilsPlan.test.js`
Expected: FAIL — plans don't include `Expected fix:` or `Completion checklist`

- [ ] **Step 3: Update renderViolationEntry() and _buildPlanLines()**

In `renderViolationEntry()`, add after the reason/CWE block and before the snippet block:

```js
function renderViolationEntry(v, index, { principleKey, reasonKey }) {
  const lines = [];
  const loc = v.file ? ` — \`${v.file}${v.line ? `:${v.line}` : ''}\`` : '';
  const principle = v[principleKey] || 'Violation';
  const reason = v[reasonKey];

  lines.push(`### ${index + 1}. ${principle}${loc}`);

  if (reason) {
    lines.push('', `**Why it's a violation:** ${reason}`);
  }

  const hint = getFixHint(v.req);
  if (hint) {
    lines.push('', `**Expected fix:** ${hint}`);
  }

  if (v.cwe) {
    lines.push('', `**Reference:** CWE-${v.cwe}`);
  }

  if (v.snippet) {
    lines.push('', '**Affected code:**');
    lines.push('```');
    v.snippet.split('\n').forEach((l) => lines.push(l));
    lines.push('```');
  }

  lines.push('');
  return lines;
}
```

In `_buildPlanLines()`, append the checklist after `PLAN_TEST_INSTRUCTION_GROUP`:

```js
  lines.push(...PLAN_OUTPUT_INSTRUCTIONS);
  lines.push(PLAN_TEST_INSTRUCTION_GROUP);
  lines.push('', PLAN_COMPLETION_CHECKLIST);
  return lines.join('\n').trim();
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd src/quodeq/ui && node --test src/utils/explorerUtilsPlan.test.js`
Expected: All PASS

Note: The existing test `buildDimensionPlanFromViolations includes PLAN_TEST_INSTRUCTION_GROUP at end` asserts `result.endsWith(PLAN_TEST_INSTRUCTION_GROUP)`. This will now fail because the checklist comes after. **Reason for modifying test:** the test asserts that `PLAN_TEST_INSTRUCTION_GROUP` is the last thing in the plan, but the checklist intentionally goes after it. Update the assertion:

```js
test('buildDimensionPlanFromViolations includes PLAN_TEST_INSTRUCTION_GROUP', () => {
  const result = buildDimensionPlanFromViolations('Performance', sampleViolations);
  assert.ok(result.includes(PLAN_TEST_INSTRUCTION_GROUP));
});
```

- [ ] **Step 5: Run full test suite**

Run: `cd src/quodeq/ui && node --test src/utils/explorerUtilsPlan.test.js && npm run build`
Expected: All tests pass, build succeeds

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/ui/src/utils/explorerUtils.js src/quodeq/ui/src/utils/explorerUtilsPlan.test.js
git commit -m "feat: wire fix hints and completion checklist into dimension plans"
```

---

### Task 4: Wire hints and checklist into PrincipleDetailPage plans

**Files:**
- Modify: `src/quodeq/ui/src/features/explorer/components/PrincipleDetailPage.jsx`

- [ ] **Step 1: Add import**

Add `getFixHint` and `PLAN_COMPLETION_CHECKLIST` to the import from `explorerUtils.js`:

```js
import { PLAN_TEST_INSTRUCTION_GROUP, PLAN_COMPLETION_CHECKLIST, getFixHint } from '../../../utils/explorerUtils.js';
```

- [ ] **Step 2: Update buildPrinciplePlanText()**

In the `vs.forEach` loop, after the reason line, add the hint:

```js
      if (v.reason) lines.push('', `**Why it's a violation:** ${v.reason}`);
      const hint = getFixHint(v.req);
      if (hint) lines.push('', `**Expected fix:** ${hint}`);
```

At the end of the function, before `return`, append the checklist:

```js
  lines.push(PLAN_TEST_INSTRUCTION_GROUP);
  lines.push('', PLAN_COMPLETION_CHECKLIST);
  return lines.join('\n').trim();
```

- [ ] **Step 3: Update buildViolationPlanText()**

After the reason line, add:

```js
  if (v.reason) lines.push('', "## Why It's a Violation", v.reason);
  const hint = getFixHint(v.req);
  if (hint) lines.push('', `**Expected fix:** ${hint}`);
```

Note: single-violation plans do NOT get the completion checklist.

- [ ] **Step 4: Build to verify**

Run: `cd src/quodeq/ui && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/ui/src/features/explorer/components/PrincipleDetailPage.jsx
git commit -m "feat: add fix hints to PrincipleDetailPage plans"
```

---

### Task 5: Wire hints and checklist into EvalPrincipleDetailPage plans

**Files:**
- Modify: `src/quodeq/ui/src/features/explorer/components/EvalPrincipleDetailPage.jsx`

- [ ] **Step 1: Add import**

```js
import { PLAN_TEST_INSTRUCTION_GROUP, PLAN_TEST_INSTRUCTION_SINGLE, PLAN_COMPLETION_CHECKLIST, getFixHint } from '../../../utils/explorerUtils.js';
```

Remove the now-redundant import of `PLAN_TEST_INSTRUCTION_GROUP` and `PLAN_TEST_INSTRUCTION_SINGLE` if they were imported from a different path.

- [ ] **Step 2: Update buildPrinciplePlanText()**

In the `vs.forEach` loop, after the reason line:

```js
      if (v.reason) lines.push('', `**Why it's a violation:** ${v.reason}`);
      const hint = getFixHint(v.req);
      if (hint) lines.push('', `**Expected fix:** ${hint}`);
```

Before `return`, append checklist:

```js
  lines.push(PLAN_TEST_INSTRUCTION_GROUP);
  lines.push('', PLAN_COMPLETION_CHECKLIST);
  return lines.join('\n').trim();
```

- [ ] **Step 3: Update buildViolationPlanText()**

After the reason line:

```js
  if (v.reason) lines.push('', "## Why It's a Violation", v.reason);
  const hint = getFixHint(v.req);
  if (hint) lines.push('', `**Expected fix:** ${hint}`);
```

No checklist for single violations.

- [ ] **Step 4: Build to verify**

Run: `cd src/quodeq/ui && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/ui/src/features/explorer/components/EvalPrincipleDetailPage.jsx
git commit -m "feat: add fix hints to EvalPrincipleDetailPage plans"
```

---

### Task 6: Wire hints and checklist into FileDetailPage plans

**Files:**
- Modify: `src/quodeq/ui/src/features/explorer/components/FileDetailPage.jsx`

- [ ] **Step 1: Add import**

```js
import { PLAN_TEST_INSTRUCTION_GROUP, PLAN_TEST_INSTRUCTION_SINGLE, PLAN_COMPLETION_CHECKLIST, getFixHint } from '../../../utils/explorerUtils.js';
```

- [ ] **Step 2: Update buildFilePlanText()**

In the `vs.forEach` loop, after the reason line:

```js
      if (v.reason) lines.push('', `**Why it's a violation:** ${v.reason}`);
      const hint = getFixHint(v.req);
      if (hint) lines.push('', `**Expected fix:** ${hint}`);
```

Before `return`, append checklist:

```js
  lines.push(PLAN_TEST_INSTRUCTION_GROUP);
  lines.push('', PLAN_COMPLETION_CHECKLIST);
  return lines.join('\n').trim();
```

- [ ] **Step 3: Update buildViolationPlanText()**

After the reason line:

```js
  if (v.reason) lines.push('', "## Why It's a Violation", v.reason);
  const hint = getFixHint(v.req);
  if (hint) lines.push('', `**Expected fix:** ${hint}`);
```

- [ ] **Step 4: Build and run full test suite**

Run: `cd src/quodeq/ui && npm run build && node --test src/utils/explorerUtilsPlan.test.js`
Expected: Build succeeds, all tests pass

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/ui/src/features/explorer/components/FileDetailPage.jsx
git commit -m "feat: add fix hints to FileDetailPage plans"
```

---

### Task 7: Final verification

- [ ] **Step 1: Run full Python test suite**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/ -x -q`
Expected: All tests pass (no Python changes, but verify nothing broke)

- [ ] **Step 2: Run full frontend build**

Run: `cd src/quodeq/ui && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Run JS tests**

Run: `cd src/quodeq/ui && node --test src/utils/explorerUtilsPlan.test.js`
Expected: All tests pass

- [ ] **Step 4: Verify by grepping for the new patterns**

```bash
grep -c "Expected fix" src/quodeq/ui/src/utils/explorerUtils.js  # should be ≥ 1
grep -c "getFixHint" src/quodeq/ui/src/utils/explorerUtils.js    # should be ≥ 2
grep -c "PLAN_COMPLETION_CHECKLIST" src/quodeq/ui/src/utils/explorerUtils.js  # should be ≥ 2
grep -c "getFixHint" src/quodeq/ui/src/features/explorer/components/PrincipleDetailPage.jsx  # should be ≥ 2
grep -c "getFixHint" src/quodeq/ui/src/features/explorer/components/EvalPrincipleDetailPage.jsx  # should be ≥ 2
grep -c "getFixHint" src/quodeq/ui/src/features/explorer/components/FileDetailPage.jsx  # should be ≥ 2
```

- [ ] **Step 5: Push**

```bash
git push
```
