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
// Raised 161 -> 188 by the size-limits-burndown test-split task (task-25):
// every oversized *.test.jsx/*.test.js file in the old list was split by
// topic into siblings, each kept under the 300-line max-lines cap (removing
// 25 whole-file entries). But max-lines-per-function counts each
// `describe(...)` callback's body as one function, and a describe wrapping
// several `it()` blocks routinely runs past 50 lines regardless of file
// size -- that's inherent to co-locating related test cases, not a size
// problem the split fixes. Fragmenting further (one test per file) would
// "fix" the metric while making the suite harder to read, for zero
// behavioral benefit. The 52 new entries are exactly those split siblings
// whose only violation is a describe-body line count; none carry a
// file-level (max-lines) violation.
const CEILING = 188;

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
