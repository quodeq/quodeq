#!/usr/bin/env node
// Ratchet gate for accessibility violations in production UI code (jsx-a11y).
//
// Existing violations are grandfathered per-file in tools/a11y_baseline.json
// so the gate runs green today while blocking NEW ones. The baseline only
// shrinks: when a file's count drops, lock the progress in with:
//     npm run lint:a11y:update
import { main } from './ratchet.mjs';
import jsxA11y from 'eslint-plugin-jsx-a11y';

// Revise DOWNWARD as burn-down tasks land; NEVER raise without a
// justification reviewed in the PR that raises it.
const TOTAL_CEILING = 64; // set to the total printed by --update after the sweep

main({
  script: 'check_a11y.mjs',
  configPath: 'eslint.a11y.config.js',
  baselinePath: 'tools/a11y_baseline.json',
  rules: Object.keys(jsxA11y.rules).map((r) => `jsx-a11y/${r}`),
  ceiling: TOTAL_CEILING,
  noun: 'accessibility violations',
  found: 'accessibility violation(s)',
  hint: 'Give the element the semantics it needs (a real <button>, role + tabIndex + activateOnKey from src/utils/a11y.js, an aria-label through t()). Run `npx eslint --no-inline-config -c eslint.a11y.config.js <file>` for details.',
  updateCommand: 'npm run lint:a11y:update',
});
