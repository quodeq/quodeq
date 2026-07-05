import { test } from 'node:test';
import assert from 'node:assert/strict';
import { deriveEvaluatePreselect } from './evaluatePreselect.js';

test('explorer page preselects its dimension', () => {
  assert.deepEqual(
    deriveEvaluatePreselect({ page: 'explorer', dimension: 'security' }),
    ['security'],
  );
});

test('evalprinciple page preselects the containing dimension', () => {
  assert.deepEqual(
    deriveEvaluatePreselect({ page: 'evalprinciple', evalPrincipal: { dimension: 'reliability' } }),
    ['reliability'],
  );
});

test('eval-principle-detail alias also preselects', () => {
  assert.deepEqual(
    deriveEvaluatePreselect({ page: 'eval-principle-detail', evalPrincipal: { dimension: 'reliability' } }),
    ['reliability'],
  );
});

test('overview and other pages preselect nothing', () => {
  assert.deepEqual(deriveEvaluatePreselect({ page: 'overview' }), []);
  assert.deepEqual(deriveEvaluatePreselect({ page: 'violations' }), []);
});

test('missing fields are guarded', () => {
  assert.deepEqual(deriveEvaluatePreselect({ page: 'explorer' }), []);
  assert.deepEqual(deriveEvaluatePreselect({ page: 'evalprinciple', evalPrincipal: {} }), []);
  assert.deepEqual(deriveEvaluatePreselect(null), []);
  assert.deepEqual(deriveEvaluatePreselect(undefined), []);
});

test('empty-string dimension is treated as no context', () => {
  // buildEvalPrincipal (App.jsx) normalizes a missing dimension to '', and the
  // explorer nav entry does the same, so the empty-string case is what
  // production actually sends when there is no real dimension.
  assert.deepEqual(deriveEvaluatePreselect({ page: 'explorer', dimension: '' }), []);
  assert.deepEqual(deriveEvaluatePreselect({ page: 'evalprinciple', evalPrincipal: { dimension: '' } }), []);
});
