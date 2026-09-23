// The magic-number ratchet burned its baseline to zero. This pins it
// there: an entry creeping back in means a new literal was grandfathered
// instead of named.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

test('the magic-number baseline stays empty', () => {
  const baseline = JSON.parse(readFileSync(join(here, 'magic_baseline.json'), 'utf8'));
  assert.deepEqual(baseline, {});
});

test('the magic-number ceiling stays at zero', () => {
  const source = readFileSync(join(here, 'check_magic.mjs'), 'utf8');
  assert.match(source, /const TOTAL_CEILING = 0;/);
});
