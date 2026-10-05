import test from 'node:test';
import assert from 'node:assert/strict';
import { ERROR_RETRY_MS, WARMUP_POLL_MS, refetchWhileError, refetchWhilePendingOrError } from './queryDefaults.js';

const query = (state) => ({ state: { data: undefined, error: null, ...state } });

test('refetchWhileError polls only while the query holds an error', () => {
  assert.equal(refetchWhileError(query({ error: new Error('x') })), ERROR_RETRY_MS);
  assert.equal(refetchWhileError(query({ data: { ok: 1 } })), false);
});

test('refetchWhilePendingOrError polls a payload the server reported as still warming', () => {
  assert.equal(refetchWhilePendingOrError(query({ data: { pending: true, warmup: {} } })), WARMUP_POLL_MS);
  assert.equal(refetchWhilePendingOrError(query({ data: { dimensions: [] } })), false);
  assert.equal(refetchWhilePendingOrError(query({ error: new Error('x') })), ERROR_RETRY_MS);
  assert.equal(refetchWhilePendingOrError(query({})), false);
});
