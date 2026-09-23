// The clone ratchet burned its baseline to zero: the Python clones went into
// shared helpers, the UI tool clones into tools/_ratchet_common.mjs and
// tools/_token_utils.mjs. This pins it there --
// an entry creeping back in means a copy-paste was grandfathered instead of
// extracted.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

test('the clone baseline stays empty', () => {
  const baseline = JSON.parse(readFileSync(join(here, 'clones_baseline.json'), 'utf8'));
  assert.deepEqual(baseline, []);
});

test('the clone ceiling stays at zero', () => {
  const source = readFileSync(join(here, 'check_clones.mjs'), 'utf8');
  assert.match(source, /const TOTAL_CEILING = 0;/);
});
