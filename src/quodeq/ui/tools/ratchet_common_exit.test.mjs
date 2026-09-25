import test from 'node:test';
import assert from 'node:assert/strict';
import { exitWith, okSummary } from './_ratchet_common.mjs';

test('okSummary names the gate noun, the grandfathered total and the file count', () => {
  assert.equal(okSummary('magic numbers', { 'a.js': 2, 'b.js': 3 }), 'OK: no new magic numbers (5 grandfathered across 2 files).');
});

test('exitWith exits with the code the gate run resolves to', async () => {
  const codes = [];
  await exitWith(Promise.resolve(1), (code) => codes.push(code));
  assert.deepEqual(codes, [1]);
});

test('exitWith reports a crashed gate run and exits 2', async (t) => {
  const errors = [];
  t.mock.method(console, 'error', (msg) => errors.push(msg));
  const codes = [];
  await exitWith(Promise.reject(new Error('boom')), (code) => codes.push(code));
  assert.deepEqual([errors, codes], [['boom'], [2]]);
});
