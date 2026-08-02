import test from 'node:test';
import assert from 'node:assert/strict';
import { readJSON, readString, removeKey, writeJSON, writeString } from './storage.js';

/** Minimal in-memory backend matching the Storage interface we use. */
const fake = (entries = {}) => ({
  data: { ...entries },
  getItem(key) { return key in this.data ? this.data[key] : null; },
  setItem(key, value) { this.data[key] = String(value); },
  removeItem(key) { delete this.data[key]; },
});

/** A backend that throws on every operation (private mode, quota exceeded). */
const hostile = () => ({
  getItem() { throw new Error('SecurityError'); },
  setItem() { throw new Error('QuotaExceededError'); },
  removeItem() { throw new Error('SecurityError'); },
});

test('readString returns the stored value', () => {
  assert.equal(readString('k', null, fake({ k: 'v' })), 'v');
});

test('readString returns the fallback when the key is absent', () => {
  assert.equal(readString('missing', 'dflt', fake()), 'dflt');
});

test('readString returns the fallback when the backend throws', () => {
  assert.equal(readString('k', 'dflt', hostile()), 'dflt');
});

test('writeString persists and reports success', () => {
  const s = fake();
  assert.equal(writeString('k', 'v', s), true);
  assert.equal(s.data.k, 'v');
});

test('writeString reports failure instead of throwing', () => {
  assert.equal(writeString('k', 'v', hostile()), false);
});

test('readJSON parses objects and arrays', () => {
  const s = fake({ obj: '{"a":1}', arr: '[1,2]' });
  assert.deepEqual(readJSON('obj', null, s), { a: 1 });
  assert.deepEqual(readJSON('arr', null, s), [1, 2]);
});

test('readJSON returns the fallback on malformed JSON', () => {
  assert.deepEqual(readJSON('k', { safe: true }, fake({ k: '{nope' })), { safe: true });
});

test('readJSON returns the fallback when absent or when the backend throws', () => {
  assert.equal(readJSON('missing', null, fake()), null);
  assert.equal(readJSON('k', null, hostile()), null);
});

test('writeJSON round-trips through readJSON', () => {
  const s = fake();
  assert.equal(writeJSON('k', { a: [1, 2] }, s), true);
  assert.deepEqual(readJSON('k', null, s), { a: [1, 2] });
});

test('writeJSON reports failure on an unserializable value', () => {
  const cyclic = {};
  cyclic.self = cyclic;
  assert.equal(writeJSON('k', cyclic, fake()), false);
});

test('removeKey deletes and never throws', () => {
  const s = fake({ k: 'v' });
  removeKey('k', s);
  assert.equal(s.getItem('k'), null);
  removeKey('k', hostile()); // must not throw
});

test('a null backend degrades to fallbacks instead of crashing', () => {
  assert.equal(readString('k', 'dflt', null), 'dflt');
  assert.equal(writeString('k', 'v', null), false);
  assert.equal(readJSON('k', null, null), null);
  removeKey('k', null);
});
