#!/usr/bin/env node
// Ratchet gate for unused bindings and over-long parameter lists in the UI.
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
const TOTAL_CEILING = 147; // set to the total printed by --update; lower it as entries burn down

main({
  script: 'check_hygiene.mjs',
  configPath: 'eslint.hygiene.config.js',
  baselinePath: 'tools/hygiene_baseline.json',
  rules: ['no-unused-vars', 'max-params', 'no-restricted-syntax'],
  ceiling: TOTAL_CEILING,
  noun: 'hygiene violations',
  found: 'unused binding(s) or over-long parameter list(s)',
  hint: 'Delete the unused binding (prefix with _ if it must stay), or pass an options object instead of more than 6 parameters. Run `npx eslint --no-inline-config -c eslint.hygiene.config.js <file>` for details.',
  updateCommand: 'npm run lint:hygiene:update',
});
