import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeComplianceByPrinciple, buildEvalPrincipalFn } from './evalPrincipal.js';

test('computeComplianceByPrinciple groups compliance findings by principle', () => {
  const evalData = { compliance: [{ principle: 'A' }, { principle: 'A' }, { principle: 'B' }] };
  const map = computeComplianceByPrinciple(evalData);
  assert.equal(map.get('A').length, 2);
  assert.equal(map.get('B').length, 1);
});

test('buildEvalPrincipalFn builds a principal object from principles/grades', () => {
  const evalData = {
    dimension: 'security',
    principles: [{ name: 'A', violations: [{ file: 'x.py' }] }],
    principleGrades: [{ principle: 'A', score: 90, grade: 'A' }],
  };
  const complianceByPrinciple = computeComplianceByPrinciple({ compliance: [] });
  const build = buildEvalPrincipalFn(evalData, complianceByPrinciple, 'proj', 'run1', '2026-09-03');
  const result = build('A');
  assert.equal(result.principle, 'A');
  assert.equal(result.score, 90);
  assert.equal(result.dimViolations.length, 1);
});
