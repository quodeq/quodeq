import test from 'node:test';
import assert from 'node:assert/strict';
import { SEVERITY_OPTIONS, toggleInList, computePrincipleOptions, filterViolations } from './dimensionCardModel.js';

test('SEVERITY_OPTIONS: the fixed severity vocabulary', () => {
  assert.deepEqual(SEVERITY_OPTIONS, ['critical', 'major', 'minor', 'unknown']);
});

// ---------------------------------------------------------------------------
// toggleInList
// ---------------------------------------------------------------------------

test('toggleInList: adds a value not yet in the list', () => {
  assert.deepEqual(toggleInList(['critical'], 'major'), ['critical', 'major']);
});

test('toggleInList: removes a value already in the list', () => {
  assert.deepEqual(toggleInList(['critical', 'major'], 'critical'), ['major']);
});

test('toggleInList: does not mutate the input list', () => {
  const list = ['critical'];
  toggleInList(list, 'major');
  assert.deepEqual(list, ['critical']);
});

// ---------------------------------------------------------------------------
// computePrincipleOptions
// ---------------------------------------------------------------------------

test('computePrincipleOptions: returns [] for a null/undefined dimension', () => {
  assert.deepEqual(computePrincipleOptions(null), []);
  assert.deepEqual(computePrincipleOptions(undefined), []);
});

test('computePrincipleOptions: unions principle names with violation principles, sorted, deduped', () => {
  const dimension = {
    principles: [{ name: 'Zeta' }, { name: 'Alpha' }],
    violations: [{ principle: 'Alpha' }, { principle: 'Beta' }, {}],
  };
  assert.deepEqual(computePrincipleOptions(dimension), ['Alpha', 'Beta', 'Zeta']);
});

test('computePrincipleOptions: drops falsy names', () => {
  const dimension = { principles: [{ name: '' }, { name: null }], violations: [] };
  assert.deepEqual(computePrincipleOptions(dimension), []);
});

// ---------------------------------------------------------------------------
// filterViolations
// ---------------------------------------------------------------------------

const DIMENSION = {
  violations: [
    { severity: 'critical', principle: 'Auth', file: 'src/Login.jsx' },
    { severity: 'minor', principle: 'Input', file: 'src/Form.jsx' },
    { severity: undefined, principle: 'Auth', file: 'src/Session.jsx' }, // unknown severity
  ],
};

test('filterViolations: returns [] for a null dimension', () => {
  assert.deepEqual(filterViolations(null, [], [], ''), []);
});

test('filterViolations: no filters selected returns every violation', () => {
  assert.equal(filterViolations(DIMENSION, [], [], '').length, 3);
});

test('filterViolations: severity filter matches, missing severity treated as "unknown"', () => {
  const result = filterViolations(DIMENSION, ['unknown'], [], '');
  assert.equal(result.length, 1);
  assert.equal(result[0].file, 'src/Session.jsx');
});

test('filterViolations: principle filter narrows to matching principles only', () => {
  const result = filterViolations(DIMENSION, [], ['Input'], '');
  assert.equal(result.length, 1);
  assert.equal(result[0].principle, 'Input');
});

test('filterViolations: file filter is case-insensitive and trims whitespace', () => {
  const result = filterViolations(DIMENSION, [], [], '  LOGIN  ');
  assert.equal(result.length, 1);
  assert.equal(result[0].file, 'src/Login.jsx');
});

test('filterViolations: combined filters intersect (AND, not OR)', () => {
  const result = filterViolations(DIMENSION, ['critical'], ['Auth'], 'login');
  assert.equal(result.length, 1);
  assert.equal(result[0].file, 'src/Login.jsx');
  assert.deepEqual(filterViolations(DIMENSION, ['critical'], ['Input'], ''), []);
});
