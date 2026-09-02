#!/usr/bin/env node
// Count-lock for the size-ratchet grandfather list (SIZE_GRANDFATHER in
// tools/size_grandfather.mjs). Same pattern as the layer-import baseline
// ceiling in tests/tools/test_import_layers.py: the list may only shrink.
// Splitting a file and removing its entry is always allowed; adding one
// requires lowering nothing here, but growth past the ceiling fails the
// build on purpose so a new violation cannot be quietly grandfathered in.
import { SIZE_GRANDFATHER } from './size_grandfather.mjs';

// Revise DOWNWARD as refactor tasks burn entries; NEVER raise without a
// justification reviewed in the PR that raises it.
//
// Lowered 161 -> 74 by the size-limits-burndown test-split task (task-25):
// every oversized *.test.jsx/*.test.js file was split by topic into
// siblings, each under the 300-line max-lines cap. Test files are now also
// exempt from max-lines-per-function in eslint.size.config.js (ESLint
// counts a describe(...) callback's body as one function, so a describe
// wrapping several `it()` blocks routinely runs past 50 lines regardless
// of file size -- not a real size problem). With that exemption, zero test
// files remain in this list; the 74 entries are all pre-existing
// production-code max-lines / max-lines-per-function violations, unrelated
// to this task.
const CEILING = 55;

const count = SIZE_GRANDFATHER.length;
if (count > CEILING) {
  console.error(
    `Size grandfather list grew to ${count} entries (ceiling ${CEILING}). ` +
      'Split the new offender instead of grandfathering it. If growth is ' +
      'truly justified, raise CEILING in tools/check_size_grandfather.mjs ' +
      'in the same PR and explain why.',
  );
  process.exit(1);
}
console.log(`OK: size grandfather list has ${count} entries (ceiling ${CEILING}).`);
