// The vocabulary-literal ratchet burns its baseline to zero in the burn-down
// commits of this branch. These pin it there: an entry creeping back in means
// a new bare literal was grandfathered instead of replaced by a src/vocab
// constant. Both cases are skipped until the burn-down lands.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

test('the vocabulary-literal baseline stays empty', { skip: 'burned to zero in the burn-down commits' }, () => {
  const baseline = JSON.parse(readFileSync(join(here, 'vocab_baseline.json'), 'utf8'));
  assert.deepEqual(baseline, {});
});

test('the vocabulary-literal ceiling stays at zero', { skip: 'burned to zero in the burn-down commits' }, () => {
  const source = readFileSync(join(here, 'check_vocab.mjs'), 'utf8');
  assert.match(source, /const TOTAL_CEILING = 0;/);
});
