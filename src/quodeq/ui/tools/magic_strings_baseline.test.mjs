// The magic-string ratchet burned its baseline to zero. This pins it there:
// an entry creeping back in means a literal was grandfathered instead of named.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

test('the magic-string baseline stays empty', () => {
  const baseline = JSON.parse(readFileSync(join(here, 'magic_strings_baseline.json'), 'utf8'));
  assert.deepEqual(baseline, {});
});

test('the magic-string ceiling stays at zero', () => {
  const source = readFileSync(join(here, 'check_magic_strings.mjs'), 'utf8');
  assert.match(source, /const TOTAL_CEILING = 0;/);
});
