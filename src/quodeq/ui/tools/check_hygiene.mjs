#!/usr/bin/env node
// Ratchet gate for unused bindings, over-long parameter lists, deep nesting,
// over-complex functions and undocumented exports in the UI.
//
// Existing violations are grandfathered per-file in tools/hygiene_baseline.json
// so the gate runs green today while blocking NEW ones. The baseline only
// shrinks: when a file's count drops, lock the progress in with:
//     npm run lint:hygiene:update
//
// The runner (per-file counts, --update, ceiling check) is tools/ratchet.mjs,
// shared with check_magic.mjs; this file only names the config, the rules and
// the messages. Reads eslint.hygiene.config.js with inline config disabled so
// an eslint-disable comment cannot waive a rule.
import { main } from './ratchet.mjs';

// Revise DOWNWARD as burn-down tasks land; NEVER raise without a
// justification reviewed in the PR that raises it.
// 2026-09: lowered from 172 to 32 once no-unused-vars burned down to zero.
// Everything left is complexity (M-MOD-1); no-unused-vars, max-params,
// max-depth and jsdoc/require-jsdoc all carry zero, so any new one fails the
// gate outright.
const TOTAL_CEILING = 32; // set to the total printed by --update; lower it as entries burn down

main({
  script: 'check_hygiene.mjs',
  configPath: 'eslint.hygiene.config.js',
  baselinePath: 'tools/hygiene_baseline.json',
  rules: ['no-unused-vars', 'max-params', 'max-depth', 'complexity', 'no-restricted-syntax', 'jsdoc/require-jsdoc'],
  ceiling: TOTAL_CEILING,
  noun: 'hygiene violations',
  found: 'unused binding(s), over-long parameter list(s), deep nesting or over-complex function(s)',
  hint: 'Delete the unused binding (prefix with _ if it must stay), pass an options object instead of more than 6 parameters, extract the nested/branching logic into named functions (max depth 4, max complexity 15), or add a JSDoc block to the new export under src/hooks, src/api, src/utils or src/features/*/hooks. Run `npx eslint --no-inline-config -c eslint.hygiene.config.js <file>` for details.',
  updateCommand: 'npm run lint:hygiene:update',
});
