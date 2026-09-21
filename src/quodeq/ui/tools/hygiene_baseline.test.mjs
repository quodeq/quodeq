// The hygiene ratchet burned its last grandfathered entries -- 30 over-complex
// functions across 26 files -- to zero in maintainability cycle 3 (PR 6). This
// pins it there: an entry creeping back in means a function was grandfathered
// instead of split.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

test('the hygiene baseline stays empty', () => {
  const baseline = JSON.parse(readFileSync(join(here, 'hygiene_baseline.json'), 'utf8'));
  assert.deepEqual(baseline, {});
});

test('the hygiene ceiling stays at zero', () => {
  const source = readFileSync(join(here, 'check_hygiene.mjs'), 'utf8');
  assert.match(source, /const TOTAL_CEILING = 0;/);
});
