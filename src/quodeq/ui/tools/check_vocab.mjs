#!/usr/bin/env node
// Ratchet gate for bare vocabulary literals in production UI code.
//
// Existing violations are grandfathered per-file in tools/vocab_baseline.json
// so the gate runs green today while blocking NEW ones. The baseline only
// shrinks: when a file's count drops, lock the progress in with:
//     npm run lint:vocab:update
//
// The runner (per-file counts, --update, ceiling check) is tools/ratchet.mjs,
// shared with check_magic.mjs; this file only names the config, the rule and
// the messages. Reads eslint.vocab.config.js with inline config disabled so
// an eslint-disable comment cannot waive the rule.
import { main } from './ratchet.mjs';

// Revise DOWNWARD as burn-down tasks land; NEVER raise without a
// justification reviewed in the PR that raises it.
const TOTAL_CEILING = 0; // burn-down complete; every file uses the src/vocab/*.js constants

main({
  script: 'check_vocab.mjs',
  configPath: 'eslint.vocab.config.js',
  baselinePath: 'tools/vocab_baseline.json',
  rules: ['no-restricted-syntax'],
  ceiling: TOTAL_CEILING,
  noun: 'vocabulary literals',
  found: 'bare vocabulary literal(s)',
  hint: 'Import the constant from src/vocab/<runState|jobStatus|exitReason|severity|grade|dimState|findingType>.js. Run `npx eslint --no-inline-config -c eslint.vocab.config.js <file>` for details.',
  updateCommand: 'npm run lint:vocab:update',
});
