import { test } from 'node:test';
import assert from 'node:assert/strict';
import { backoffDelay } from './backoff.js';

function withFixedRandom(value, fn) {
  const original = Math.random;
  Math.random = () => value;
  try {
    return fn();
  } finally {
    Math.random = original;
  }
}

test('backoffDelay: at attempt 0, before jitter, equals baseMs', () => {
  withFixedRandom(0, () => {
    assert.equal(backoffDelay(0, 500, 5000), 250); // 500 * 0.5 jitter floor
  });
  withFixedRandom(0.999999999, () => {
    assert.ok(backoffDelay(0, 500, 5000) < 500);
  });
});

test('backoffDelay: doubles per attempt before the cap', () => {
  withFixedRandom(0, () => {
    assert.equal(backoffDelay(0, 100, 100000), 50);
    assert.equal(backoffDelay(1, 100, 100000), 100);
    assert.equal(backoffDelay(2, 100, 100000), 200);
    assert.equal(backoffDelay(3, 100, 100000), 400);
  });
});

test('backoffDelay: never exceeds maxMs, even after jitter', () => {
  withFixedRandom(0.999999999, () => {
    const delay = backoffDelay(20, 500, 5000);
    assert.ok(delay <= 5000);
  });
});

test('backoffDelay: caps the exponential growth at maxMs before jitter is applied', () => {
  withFixedRandom(0, () => {
    // Uncapped this would be 500 * 2**20, far past maxMs.
    assert.equal(backoffDelay(20, 500, 5000), 2500); // 5000 * 0.5 jitter floor
  });
});

test('backoffDelay: is jittered (not the same value on every call)', () => {
  const values = new Set();
  for (let i = 0; i < 20; i += 1) values.add(backoffDelay(0, 1000, 10000));
  assert.ok(values.size > 1);
});

test('backoffDelay: a later attempt always waits at least as long as an earlier one, even with jitter', () => {
  // attempt N's minimum (base*2**N * 0.5) is >= attempt N-1's maximum
  // (base*2**(N-1) * <1), so growth holds regardless of the random draw.
  for (let i = 0; i < 50; i += 1) {
    const earlier = backoffDelay(0, 200, 100000);
    const later = backoffDelay(1, 200, 100000);
    assert.ok(later >= earlier, `attempt 1 (${later}) should be >= attempt 0 (${earlier})`);
  }
});
