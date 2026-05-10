import test from 'node:test';
import assert from 'node:assert/strict';
import { abbrevDim, DIM_ABBREV } from './dimAbbrev.js';

test('abbreviates known dimensions to their canonical short forms', () => {
  assert.equal(abbrevDim('security'), 'sec');
  assert.equal(abbrevDim('Maintainability'), 'maint');
  assert.equal(abbrevDim('PERFORMANCE'), 'perf');
  assert.equal(abbrevDim('reliability'), 'rel');
  assert.equal(abbrevDim('flexibility'), 'flex');
  assert.equal(abbrevDim('usability'), 'usab');
});

test('passes short unknown dims through lowercased', () => {
  assert.equal(abbrevDim('foo'), 'foo');
  assert.equal(abbrevDim('AB'), 'ab');
  assert.equal(abbrevDim('FIVES'), 'fives'); // exactly 5 chars: passthrough
});

test('truncates long unknown dims to 4 chars', () => {
  assert.equal(abbrevDim('observability'), 'obse');
  assert.equal(abbrevDim('SCALABILITY'), 'scal');
});

test('returns the input as-is for falsy values', () => {
  assert.equal(abbrevDim(''), '');
  assert.equal(abbrevDim(null), null);
  assert.equal(abbrevDim(undefined), undefined);
});

test('DIM_ABBREV is exported and contains expected entries', () => {
  assert.equal(DIM_ABBREV.security, 'sec');
  assert.equal(DIM_ABBREV.maintainability, 'maint');
});
