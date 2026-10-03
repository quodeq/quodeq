import { test } from 'node:test';
import assert from 'node:assert/strict';
import { typesRows, rowSeverity } from './typesRows.js';

const v = (req, principle, severity) => ({ req, principle, file: 'a.py', line: 1, severity });
const dims = [{
  dimension: 'maintainability', fromRunId: 'r1',
  violations: [v('M-MDF-3', 'Modifiability', 'minor'), v('M-MDF-3', 'Modifiability', 'major'), v('M-ANA-9', 'Analyzability', 'critical')],
}];
const withBaseline = { r1: { dimensions: { maintainability: { againstRunId: 'r0', types: { perReq: { 'M-MDF-1': [2, 0], 'M-MDF-3': [4, 2], 'M-ANA-9': [1, 1] } } } } } };
const noBaseline = { r1: { dimensions: { maintainability: { againstRunId: null, types: { perReq: {} } } } } };
const draft = { severityWeight: { critical: 8, major: 2, minor: 0.25 } };

test('rowSeverity is the worst severity among the findings', () => {
  assert.equal(rowSeverity([v('x', 'p', 'minor'), v('x', 'p', 'major')]), 'major');
  assert.equal(rowSeverity([]), null);
});

test('typesRows adds the severity and the draft weight of each type', () => {
  const rows = typesRows({ dimensions: dims, diffsByRun: withBaseline, standardsByDim: {}, draft });
  const mdf3 = rows.find((r) => r.req === 'M-MDF-3');
  assert.deepEqual([mdf3.severity, mdf3.weight, mdf3.now, mdf3.baseline, mdf3.closed], ['major', '2.0', 2, 4, false]);
  const ana9 = rows.find((r) => r.req === 'M-ANA-9');
  assert.deepEqual([ana9.severity, ana9.weight], ['critical', '8.0']);
});

test('a closed type with no findings has no severity and no weight', () => {
  const rows = typesRows({ dimensions: dims, diffsByRun: withBaseline, standardsByDim: {}, draft });
  const mdf1 = rows.find((r) => r.req === 'M-MDF-1');
  assert.deepEqual([mdf1.closed, mdf1.severity, mdf1.weight], [true, null, null]);
});

test('no baseline leaves baseline null and the row open', () => {
  const rows = typesRows({ dimensions: dims, diffsByRun: noBaseline, standardsByDim: {}, draft });
  assert.ok(rows.every((r) => r.baseline === null && !r.closed));
});

test('typesRows without a draft has no weights', () => {
  const rows = typesRows({ dimensions: dims, diffsByRun: withBaseline, standardsByDim: {}, draft: null });
  assert.ok(rows.every((r) => r.weight === null));
});
