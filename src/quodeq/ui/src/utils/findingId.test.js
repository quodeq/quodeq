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

  await t.test('round-trip with Python backend: pin end-to-end hash', () => {
    // Round-trip with the Python backend: computeFindingId composes file|line|title
    // and FNV-1a hashes it. This pins the composed value end-to-end against the
    // Python _fnv1a32 in src/quodeq/verifier/service.py.
    assert.strictEqual(
      computeFindingId({ file: 'src/api/app.py', line: 34, title: 'hardcoded provider' }),
      '8420df1b',
    );
  });

  await t.test('unpacks "file:line" packed in the file field when line is null', () => {
    // Some views (principle drilldown rows in EvalCards) pass `file:line`
    // packed in the file field with line: null. Must still produce the
    // same hash as separate fields.
    const separate = computeFindingId({
      file: 'src/quodeq/api/app.py',
      line: 34,
      title: 'Platform-specific filesystem dependency',
    });
    const packed = computeFindingId({
      file: 'src/quodeq/api/app.py:34',
      line: null,
      title: 'Platform-specific filesystem dependency',
    });
    assert.strictEqual(separate, packed);
    assert.strictEqual(separate, 'd3412c14');
  });

  await t.test('does not split when the trailing colon segment is non-numeric', () => {
    // A file with a colon but no trailing :digits should be left alone
    // (e.g. a git ref or weird path). line stays 0.
    const id = computeFindingId({ file: 'a/b:branch', line: null, title: 't' });
    assert.strictEqual(id, fnv1a32('a/b:branch|0|t'));
  });
});
