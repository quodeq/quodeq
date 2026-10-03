import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildTypeRows, groupRows, requirementIndex } from './byTypeModel.js';

const standard = { id: 'maintainability', principles: [
  { name: 'Modifiability', requirements: [{ id: 'M-MDF-1', text: 'No magic literals' }, { id: 'M-MDF-3', text: 'Small functions' }] },
  { name: 'Analyzability', requirements: [{ id: 'M-ANA-9', text: 'Short files' }] },
] };
const v = (req, principle, file = 'a.py') => ({ req, principle, file, line: 1, severity: 'minor' });
const dim = (over = {}) => ({
  dimension: 'maintainability', fromRunId: 'r1', fromDateLabel: '26 Sep',
  violations: [v('M-MDF-3', 'Modifiability'), v('M-MDF-3', 'Modifiability', 'b.py'), v('M-ANA-9', 'Analyzability'), v('', 'Modifiability')],
  ...over,
});
const diff = (over = {}) => ({ r1: { dimensions: { maintainability: { againstRunId: 'r0', types: { perReq: { 'M-MDF-1': [215, 0], 'M-MDF-3': [4, 2], 'M-ANA-9': [93, 1], '': [3, 1] } } } } }, ...over });

test('requirementIndex maps code to principle and text', () => {
  const idx = requirementIndex(standard);
  assert.deepEqual(idx.get('M-ANA-9'), { principle: 'Analyzability', text: 'Short files' });
  assert.equal(requirementIndex(null).size, 0);
});

test('buildTypeRows unions current types with baseline types, sorted now desc then closed last', () => {
  const rows = buildTypeRows({ dimensions: [dim()], diffsByRun: diff(), standardsByDim: { maintainability: standard } });
  assert.deepEqual(rows.map((r) => r.req), ['M-MDF-3', 'M-ANA-9', 'M-MDF-1']);
  const mdf1 = rows[2];
  assert.deepEqual([mdf1.baseline, mdf1.now, mdf1.delta, mdf1.closed, mdf1.principle, mdf1.text], [215, 0, -215, true, 'Modifiability', 'No magic literals']);
  assert.deepEqual([rows[0].baseline, rows[0].now, rows[0].delta, rows[0].violations.length], [4, 2, -2, 2]);
});

test('empty req is not a type', () => {
  const rows = buildTypeRows({ dimensions: [dim()], diffsByRun: diff(), standardsByDim: {} });
  assert.ok(rows.every((r) => r.req));
});

test('closed rows list even without standard text', () => {
  const rows = buildTypeRows({ dimensions: [dim()], diffsByRun: diff(), standardsByDim: {} });
  const mdf1 = rows.find((r) => r.req === 'M-MDF-1');
  assert.deepEqual([mdf1.closed, mdf1.principle, mdf1.text], [true, '', '']);
});

test('no baseline means no delta', () => {
  const first = diff({ r1: { dimensions: { maintainability: { againstRunId: null, types: { perReq: { 'M-MDF-3': [0, 2] } } } } } });
  const rows = buildTypeRows({ dimensions: [dim()], diffsByRun: first, standardsByDim: {} });
  const mdf3 = rows.find((r) => r.req === 'M-MDF-3');
  assert.deepEqual([mdf3.baseline, mdf3.delta, mdf3.closed], [null, null, false]);
  assert.ok(rows.every((r) => !r.closed));
});

test('a dimension whose diff has not loaded still lists its current types', () => {
  const rows = buildTypeRows({ dimensions: [dim()], diffsByRun: {}, standardsByDim: {} });
  assert.deepEqual(rows.map((r) => [r.req, r.baseline]), [['M-MDF-3', null], ['M-ANA-9', null]]);
});

test('groupRows inserts dimension and principle headers with open and closed counts', () => {
  const rows = buildTypeRows({ dimensions: [dim()], diffsByRun: diff(), standardsByDim: { maintainability: standard } });
  const grouped = groupRows(rows);
  assert.deepEqual(grouped.map((g) => g.type), ['dimension', 'principle', 'type', 'type', 'principle', 'type']);
  assert.deepEqual([grouped[0].openTypes, grouped[0].closedTypes], [2, 1]);
  assert.equal(grouped[1].name, 'Modifiability');
});
