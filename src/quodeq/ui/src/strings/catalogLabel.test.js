import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogLabel } from './labels.js';

test('catalogLabel renders a known value through the catalog under its prefix', () => {
  assert.equal(catalogLabel('scopeGateRule', ['cross_principal'])('cross_principal'), 'cross-principal');
});

test('catalogLabel passes an unknown value through unchanged', () => {
  assert.deepEqual([catalogLabel('severity', ['critical'])('weird'), catalogLabel('severity', [])(undefined)], ['weird', undefined]);
});
