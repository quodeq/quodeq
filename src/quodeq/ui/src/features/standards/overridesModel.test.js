import test from 'node:test';
import assert from 'node:assert/strict';
import { applyParamOverride, countCustomizedRequirements, decideSave } from './overridesModel.js';

// ---------------------------------------------------------------------------
// applyParamOverride
// ---------------------------------------------------------------------------

test('applyParamOverride: sets a new override for a requirement with none yet', () => {
  const next = applyParamOverride({}, 'REQ-1', 'max_lines', 60);
  assert.deepEqual(next, { 'REQ-1': { max_lines: 60 } });
});

test('applyParamOverride: adds a second param alongside an existing one', () => {
  const next = applyParamOverride({ 'REQ-1': { max_lines: 60 } }, 'REQ-1', 'min_coverage', 0.8);
  assert.deepEqual(next, { 'REQ-1': { max_lines: 60, min_coverage: 0.8 } });
});

test('applyParamOverride: null clears the param; the req key is dropped when none remain', () => {
  const next = applyParamOverride({ 'REQ-1': { max_lines: 60 } }, 'REQ-1', 'max_lines', null);
  assert.equal(next['REQ-1'], undefined);
});

test('applyParamOverride: null on one of several params keeps the requirement entry', () => {
  const next = applyParamOverride(
    { 'REQ-1': { max_lines: 60, min_coverage: 0.8 } }, 'REQ-1', 'max_lines', null,
  );
  assert.deepEqual(next, { 'REQ-1': { min_coverage: 0.8 } });
});

test('applyParamOverride: does not mutate the input overrides object', () => {
  const original = { 'REQ-1': { max_lines: 60 } };
  applyParamOverride(original, 'REQ-1', 'max_lines', 80);
  assert.deepEqual(original, { 'REQ-1': { max_lines: 60 } }); // untouched
});

test('applyParamOverride: leaves other requirements alone', () => {
  const next = applyParamOverride(
    { 'REQ-1': { max_lines: 60 }, 'REQ-2': { min_coverage: 0.5 } }, 'REQ-1', 'max_lines', 90,
  );
  assert.deepEqual(next['REQ-2'], { min_coverage: 0.5 });
});

// ---------------------------------------------------------------------------
// countCustomizedRequirements
// ---------------------------------------------------------------------------

const STANDARD = {
  principles: [
    { requirements: [{ id: 'REQ-1' }, { id: 'REQ-2' }] },
    { requirements: [{ id: 'REQ-3' }] },
  ],
};

test('countCustomizedRequirements: counts only overrides that belong to this standard', () => {
  const overrides = { 'REQ-1': { max_lines: 60 }, 'REQ-3': { max_lines: 10 }, 'OTHER-STD-REQ': { x: 1 } };
  assert.equal(countCustomizedRequirements(STANDARD, overrides), 2);
});

test('countCustomizedRequirements: zero when there are no overrides', () => {
  assert.equal(countCustomizedRequirements(STANDARD, {}), 0);
});

test('countCustomizedRequirements: handles a standard with no principles', () => {
  assert.equal(countCustomizedRequirements({}, { 'REQ-1': {} }), 0);
  assert.equal(countCustomizedRequirements(null, { 'REQ-1': {} }), 0);
});

// ---------------------------------------------------------------------------
// decideSave
// ---------------------------------------------------------------------------

test('decideSave: commits outright when there is no drafted overrides change', () => {
  assert.equal(decideSave({ overridesDirty: false, impact: { changedDimensions: ['security'] } }), 'commit');
  assert.equal(decideSave({ overridesDirty: false, impact: null }), 'commit');
});

test('decideSave: commits when the preview reports no changed dimensions', () => {
  assert.equal(decideSave({ overridesDirty: true, impact: { changedDimensions: [] } }), 'commit');
});

test('decideSave: commits when the preview omits changedDimensions entirely', () => {
  assert.equal(decideSave({ overridesDirty: true, impact: {} }), 'commit');
  assert.equal(decideSave({ overridesDirty: true, impact: null }), 'commit');
});

test('decideSave: asks for confirmation when the preview reports changed dimensions', () => {
  assert.deepEqual(
    decideSave({ overridesDirty: true, impact: { changedDimensions: ['security', 'maintainability'] } }),
    { confirm: ['security', 'maintainability'] },
  );
});
