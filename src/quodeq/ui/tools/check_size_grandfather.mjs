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
const CEILING = 219;

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
