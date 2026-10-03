#!/usr/bin/env node
// Ratchet gate for magic numbers in production UI code.
//
// Existing violations are grandfathered per-file in tools/magic_baseline.json
// so the gate runs green today while blocking NEW ones. The baseline only
// shrinks: when a file's count drops, lock the progress in with:
//     npm run lint:magic:update
//
// The runner (per-file counts, --update, ceiling check) is tools/ratchet.mjs,
// shared with check_hygiene.mjs; this file only names the config, the rule and
// the messages. Reads eslint.magic.config.js with inline config disabled so
// an eslint-disable comment cannot waive the rule.
import { main } from './ratchet.mjs';

// Revise DOWNWARD as burn-down tasks land; NEVER raise without a
// justification reviewed in the PR that raises it.
const TOTAL_CEILING = 0; // the baseline is empty: every magic number is a named constant

main({
  script: 'check_magic.mjs',
  configPath: 'eslint.magic.config.js',
  baselinePath: 'tools/magic_baseline.json',
  rules: ['no-magic-numbers'],
  ceiling: TOTAL_CEILING,
  noun: 'magic numbers',
  found: 'magic number(s)',
  hint: 'Name the literal (`const UPPER_SNAKE = value; // why`) in the module, the feature constants module, or src/constants.js. Run `npx eslint --no-inline-config -c eslint.magic.config.js <file>` for details.',
  updateCommand: 'npm run lint:magic:update',
});
