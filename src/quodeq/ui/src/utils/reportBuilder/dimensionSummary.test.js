import test from 'node:test';
import assert from 'node:assert/strict';
import { buildDimensionSummaryTable } from './dimensionSummary.js';

test('buildDimensionSummaryTable: a genuine overall score of 0 renders as 0, not the em-dash placeholder', () => {
  const lines = buildDimensionSummaryTable([
    { dimension: 'security', overallScore: 0, overallGrade: 'F', violations: [], compliance: [] },
  ]);
  const row = lines.find((l) => l.startsWith('| Security'));
  assert.equal(row, '| Security | 0 | F | 0 | 0 |');
});

test('buildDimensionSummaryTable: a missing overall score renders the em-dash placeholder', () => {
  const lines = buildDimensionSummaryTable([
    { dimension: 'security', overallScore: null, overallGrade: null, violations: [], compliance: [] },
  ]);
  const row = lines.find((l) => l.startsWith('| Security'));
  assert.equal(row, '| Security | — | — | 0 | 0 |');
});

test('buildDimensionSummaryTable: an undefined overall score renders the em-dash placeholder', () => {
  const lines = buildDimensionSummaryTable([
    { dimension: 'security', violations: [], compliance: [] },
  ]);
  const row = lines.find((l) => l.startsWith('| Security'));
  assert.equal(row, '| Security | — | — | 0 | 0 |');
});
