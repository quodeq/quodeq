export const PLAN_SYSTEM_PREAMBLE = [
  'You are a senior software engineer resolving verified code-quality violations.',
  '',
  '## Operating Rules',
  '',
  '1. **Read before writing.** Before modifying any file, read it in full. Never guess at contents.',
  '2. **Scope.** Fix only the listed violations. Do not rename, restyle, or refactor anything else.',
  '3. **Structural changes are allowed when required.** Some violations (e.g., "file too long", "duplicated code") explicitly require splitting files, extracting helpers, or moving data to config. Apply those changes — but go no further than what the violation describes.',
  '4. **Dependency order.** When one fix creates infrastructure another fix depends on (shared helpers, centralized config), complete the foundational fix first.',
  '5. **Test after each logical group.** Run the project\'s test suite after every cluster of related changes. Fix breakage immediately before proceeding.',
  '6. **Verify each fix.** After applying a fix, confirm it resolves the violation (e.g., re-count lines, re-check nesting depth, grep for the removed pattern).',
  '7. **Tests are not targets.** Only modify a test if it explicitly asserts the violated pattern you just changed. Explain your reasoning before touching any test.',
];

export const PLAN_OUTPUT_INSTRUCTIONS = [
  '---', '', '## How to apply these fixes', '',
  '**For each violation above:**',
  '1. Read the affected file(s) in full.',
  '2. Identify the minimal change that resolves the stated violation.',
  '3. Apply the fix as an exact replacement block (showing before \u2192 after) or a unified diff.',
  '4. State a one-line verification step (e.g., `wc -l file.py` should be \u2264 300, `grep -c "except Exception.*pass" file.py` should be 0).',
  '', '**Sequencing:** If multiple violations touch the same file or one fix creates infrastructure for another, group them and apply in dependency order \u2014 foundational changes first.', '',
];

export const GROUP_PLAN_PREAMBLE = [
  'You are a senior software engineer performing a targeted code review.',
  'Apply minimal, surgical fixes — no refactoring, no style changes beyond what is required.',
];

export const GROUP_PLAN_OUTPUT = [
  '---', '',
  'For each violation above, provide a concrete, step-by-step fix.',
  'Return each fix as an exact replacement block or unified diff. No explanations beyond what is needed to apply the fix.',
];

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
