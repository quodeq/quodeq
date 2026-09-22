import test from 'node:test';
import assert from 'node:assert/strict';
import { createSlimDimension } from './dimension.js';

// mergeRescoreIntoEval (explorerDataHooks.js) treats `violations != null` as a
// tri-state: an ABSENT violations key means "keep the prior Explorer
// violations", a PRESENT one (even []) means "use this to filter". Unlike
// createDimension, createSlimDimension must not coerce an absent key to [],
// or that distinction is lost and the Explorer's violations get silently
// wiped whenever a slim payload omits the key.

test('createSlimDimension preserves an absent violations key (no coercion to [])', () => {
  const dim = createSlimDimension({ dimension: 'security', overallScore: '90' });
  // undefined, not [] -- mergeRescoreIntoEval's `!= null` tri-state check
  // treats both a missing key and an explicit undefined as "absent".
  assert.equal(dim.violations, undefined);
  assert.notDeepEqual(dim.violations, []);
});

test('createSlimDimension maps a present violations array to canonical Violations', () => {
  const dim = createSlimDimension({
    dimension: 'security',
    violations: [{ file: 'a.py', line: 3, severity: 'critical' }],
  });
  assert.equal(dim.violations.length, 1);
  assert.equal(dim.violations[0].file, 'a.py');
  assert.equal(dim.violations[0].severity, 'critical');
});

test('createSlimDimension maps a present empty violations array to []', () => {
  const dim = createSlimDimension({ dimension: 'security', violations: [] });
  assert.deepEqual(dim.violations, []);
});

test('createSlimDimension preserves an absent compliance key', () => {
  const dim = createSlimDimension({ dimension: 'security' });
  assert.equal(dim.compliance, undefined);
});

test('createSlimDimension maps a present compliance array', () => {
  const dim = createSlimDimension({ dimension: 'security', compliance: [{ file: 'b.py' }] });
  assert.equal(dim.compliance.length, 1);
  assert.equal(dim.compliance[0].file, 'b.py');
});

test('createSlimDimension preserves an absent principles key', () => {
  const dim = createSlimDimension({ dimension: 'security' });
  assert.equal(dim.principles, undefined);
});

test('createSlimDimension maps a present principles array', () => {
  const dim = createSlimDimension({ dimension: 'security', principles: [{ name: 'p1' }] });
  assert.equal(dim.principles.length, 1);
  assert.equal(dim.principles[0].name, 'p1');
});

test('createSlimDimension returns non-object input unchanged', () => {
  assert.equal(createSlimDimension(null), null);
  assert.equal(createSlimDimension(undefined), undefined);
});

test('createSlimDimension passes through other fields untouched', () => {
  const dim = createSlimDimension({ dimension: 'security', overallScore: '90', overallGrade: 'A' });
  assert.equal(dim.overallScore, '90');
  assert.equal(dim.overallGrade, 'A');
});
