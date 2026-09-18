#!/usr/bin/env node
// Ratchet gate for fault-tolerance violations in production UI code:
// swallowed catches, floating promises, raw web storage access and
// unguarded dereferences of a nullable lookup.
//
// Existing violations are grandfathered per-file in tools/fault_baseline.json
// so the gate runs green today while blocking NEW ones. The baseline only
// shrinks: when a file's count drops, lock the progress in with:
//     npm run lint:fault:update
//
// The runner (per-file counts, --update, ceiling check) is tools/ratchet.mjs,
// shared with check_hygiene.mjs, check_magic.mjs and check_a11y.mjs; this file
// only names the config, the rules and the messages. Reads
// eslint.fault.config.js with inline config disabled so an eslint-disable
// comment cannot waive a rule.
import { main } from './ratchet.mjs';

// Revise DOWNWARD as burn-down tasks land; NEVER raise without a
// justification reviewed in the PR that raises it.
const TOTAL_CEILING = 17; // set to the total printed by --update after the sweep

main({
  script: 'check_fault.mjs',
  configPath: 'eslint.fault.config.js',
  baselinePath: 'tools/fault_baseline.json',
  rules: [
    'fault/swallowed-catch',
    'fault/floating-promise',
    'fault/raw-storage-access',
    'fault/unguarded-lookup-deref',
  ],
  ceiling: TOTAL_CEILING,
  noun: 'fault-tolerance violations',
  found: 'swallowed catch(es), floating promise(s), raw storage access or unguarded lookup deref(s)',
  hint: 'Log the caught error via console.warn with a [module] prefix (never delete the catch), await/return/.catch() the promise, route storage through src/adapters/storage.js, or guard the lookup with ?. before dereferencing. Run `npx eslint --no-inline-config -c eslint.fault.config.js <file>` for details.',
  updateCommand: 'npm run lint:fault:update',
});
