import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeComplianceByPrinciple, buildEvalPrincipalFn } from './evalPrincipal.js';

test('computeComplianceByPrinciple groups compliance findings by principle', () => {
  const evalData = { compliance: [{ principle: 'A' }, { principle: 'A' }, { principle: 'B' }] };
  const map = computeComplianceByPrinciple(evalData);
  assert.equal(map.get('A').length, 2);
  assert.equal(map.get('B').length, 1);
});

test('computeComplianceByPrinciple: a second entry for an already-seen principle lands in the same array (not a fresh one)', () => {
  const evalData = { compliance: [{ principle: 'A', file: 'first.py' }, { principle: 'A', file: 'second.py' }] };
  const map = computeComplianceByPrinciple(evalData);
  const entries = map.get('A');
  assert.deepEqual(entries.map((e) => e.file), ['first.py', 'second.py']);
});

test('buildEvalPrincipalFn builds a principal object from the grades and the flat violations', () => {
  const evalData = {
    dimension: 'security',
    principles: [{ name: 'A' }, { name: 'B' }],
    principleGrades: [{ principle: 'A', score: 90, grade: 'A' }],
    violations: [{ principle: 'A', file: 'x.py' }, { principle: 'B', file: 'y.py' }, { principle: 'A', file: 'z.py' }],
  };
  const complianceByPrinciple = computeComplianceByPrinciple({ compliance: [] });
  const build = buildEvalPrincipalFn(evalData, complianceByPrinciple, 'proj', 'run1', '2026-09-03');
  const result = build('A');
  assert.equal(result.principle, 'A');
  assert.equal(result.score, 90);
  assert.deepEqual(result.dimViolations.map((v) => v.file), ['x.py', 'z.py']);
  assert.equal(result.principleData, evalData.principles[0]);
  assert.deepEqual(build('C').dimViolations, []);
});

test('buildEvalPrincipalFn: a genuine score of 0 is kept, not coerced to null', () => {
  const evalData = {
    dimension: 'security',
    principles: [{ name: 'A' }],
    principleGrades: [{ principle: 'A', score: 0, grade: 'F' }],
  };
  const complianceByPrinciple = computeComplianceByPrinciple({ compliance: [] });
  const build = buildEvalPrincipalFn(evalData, complianceByPrinciple, 'proj', 'run1');
  const result = build('A');
  assert.equal(result.score, 0);
});
