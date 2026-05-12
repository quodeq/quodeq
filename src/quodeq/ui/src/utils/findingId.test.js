import test from 'node:test';
import assert from 'node:assert/strict';
import { fnv1a32, computeFindingId } from './findingId.js';

test('fnv1a32', async (t) => {
  await t.test('matches known-value pin from the Python backend', () => {
    // Pinned against quodeq/verifier/service.py::_fnv1a32 to guarantee
    // round-trip identity with the FindingNotFound locator lookup.
    assert.strictEqual(fnv1a32('src/api/app.py|34|hardcoded provider'), '8420df1b');
  });

  await t.test('produces 8 lowercase hex chars', () => {
    assert.strictEqual(fnv1a32('anything').length, 8);
    assert.match(fnv1a32('anything'), /^[0-9a-f]{8}$/);
  });

  await t.test('matches FNV-1a test vectors', () => {
    assert.strictEqual(fnv1a32(''), '811c9dc5');
    assert.strictEqual(fnv1a32('foobar'), 'bf9cf968');
  });
});

test('computeFindingId', async (t) => {
  await t.test('uses file|line|title with safe defaults for missing fields', () => {
    const a = computeFindingId({ file: 'a.py', line: 1, title: 'x' });
    const b = computeFindingId({ file: 'a.py', line: 1, title: 'x' });
    assert.strictEqual(a, b);
    // Treats missing fields as the empty/zero defaults Python does.
    assert.strictEqual(computeFindingId({}), fnv1a32('|0|'));
  });
});
