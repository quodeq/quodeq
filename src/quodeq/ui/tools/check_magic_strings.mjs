#!/usr/bin/env node
// Ratchet gate for magic strings in production UI code: a bare string the
// code compares against, or the same string three or more times in one
// module (tools/magic_string_rules.mjs).
//
// Existing violations are grandfathered per-file in
// tools/magic_strings_baseline.json. The baseline only shrinks: when a
// file's count drops, lock the progress in with:
//     npm run lint:magic-strings:update
//
// The runner (per-file counts, --update, ceiling check) is tools/ratchet.mjs.
// Reads eslint.magic-strings.config.js with inline config disabled so an
// eslint-disable comment cannot waive a rule.
import { main } from './ratchet.mjs';

// Revise DOWNWARD as burn-down tasks land; NEVER raise without a
// justification reviewed in the PR that raises it.
const TOTAL_CEILING = 214; // Task 8 sweep (keyboard vocab + shared-layer constants): 360 -> 214; burning to 0 in this PR

main({
  script: 'check_magic_strings.mjs',
  configPath: 'eslint.magic-strings.config.js',
  baselinePath: 'tools/magic_strings_baseline.json',
  rules: ['magic-str/compared-literal', 'magic-str/repeated-literal'],
  ceiling: TOTAL_CEILING,
  noun: 'magic strings',
  found: 'bare compared or repeated string literal(s)',
  hint: 'Name the literal: a module constant, the feature constants module, src/constants.js, or a src/vocab/*.js member for a closed set. Run `npx eslint --no-inline-config -c eslint.magic-strings.config.js <file>` for details.',
  updateCommand: 'npm run lint:magic-strings:update',
});
