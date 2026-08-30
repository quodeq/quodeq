import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildRows, buildDimensionGroup, buildPrincipleRow, comparator, getSortValue,
  DEFAULT_SEVERITY, newPrincipleEntry, flattenAndSort,
} from './dimensionHeatGridModel.js';

// ---------------------------------------------------------------------------
// buildDimensionGroup / buildPrincipleRow / newPrincipleEntry
// ---------------------------------------------------------------------------

test('buildDimensionGroup: returns null for a dimension with no violations or compliance', () => {
  assert.equal(buildDimensionGroup({ dimension: 'security', violations: [], compliance: [] }), null);
  assert.equal(buildDimensionGroup({ dimension: 'security' }), null);
});

test('buildDimensionGroup: groups violations and compliance by principle', () => {
  const dim = {
    dimension: 'security',
    violations: [
      { principle: 'Auth', severity: 'critical', file: 'a.py' },
      { principle: 'Auth', severity: 'major', file: 'b.py' },
      { principle: 'Input', severity: 'minor', file: 'c.py' },
    ],
    compliance: [{ principle: 'Auth', file: 'd.py' }],
  };
  const { dimRow, principles } = buildDimensionGroup(dim);
  assert.equal(dimRow.type, 'dimension');
  assert.equal(dimRow.violations, 3);
  assert.equal(dimRow.compliance, 1);
  assert.deepEqual(dimRow.severity, { critical: 1, major: 1, minor: 1 });
  assert.equal(dimRow.complianceRate, 1 / 4);

  assert.equal(principles.length, 2);
  const auth = principles.find((p) => p.name === 'Auth');
  assert.equal(auth.violations, 2);
  assert.equal(auth.compliance, 1);
  assert.equal(auth.complianceRate, 1 / 3);
  const input = principles.find((p) => p.name === 'Input');
  assert.equal(input.violations, 1);
  assert.equal(input.compliance, 0);
});

test('buildDimensionGroup: an unlisted principle groups under "(unknown)"', () => {
  const dim = { dimension: 'security', violations: [{ severity: 'minor' }], compliance: [] };
  const { principles } = buildDimensionGroup(dim);
  assert.equal(principles.length, 1);
  assert.equal(principles[0].name, '(unknown)');
});

test('buildDimensionGroup: DEFAULT_SEVERITY counts a missing severity as minor', () => {
  const dim = { dimension: 'security', violations: [{ principle: 'Auth' }], compliance: [] };
  const { dimRow } = buildDimensionGroup(dim);
  assert.equal(dimRow.severity[DEFAULT_SEVERITY], 1);
  assert.equal(DEFAULT_SEVERITY, 'minor');
});

test('buildDimensionGroup: an out-of-vocabulary severity counts toward violations/totals but no known column', () => {
  const dim = { dimension: 'security', violations: [{ principle: 'Auth', severity: 'blocker' }], compliance: [] };
  const { dimRow, principles } = buildDimensionGroup(dim);
  assert.equal(dimRow.violations, 1); // counted in the total
  assert.deepEqual(dimRow.severity, { critical: 0, major: 0, minor: 0 }); // no column bucket incremented
  assert.equal(principles[0].violations, 1);
  assert.deepEqual(principles[0].severity, { critical: 0, major: 0, minor: 0 });
});

test('newPrincipleEntry: starts every counter at zero with empty item lists', () => {
  assert.deepEqual(newPrincipleEntry(), {
    violations: 0, compliance: 0, severity: { critical: 0, major: 0, minor: 0 },
    violationItems: [], complianceItems: [],
  });
});

// ---------------------------------------------------------------------------
// getSortValue / comparator
// ---------------------------------------------------------------------------

test('getSortValue: reads the field matching each column id', () => {
  const row = { name: 'Auth', severity: { critical: 2, major: 1, minor: 0 }, violations: 3, complianceRate: 0.5 };
  assert.equal(getSortValue(row, 'name'), 'Auth');
  assert.equal(getSortValue(row, 'critical'), 2);
  assert.equal(getSortValue(row, 'major'), 1);
  assert.equal(getSortValue(row, 'minor'), 0);
  assert.equal(getSortValue(row, 'violations'), 3);
  assert.equal(getSortValue(row, 'health'), 0.5);
  assert.equal(getSortValue(row, 'nonsense'), 0);
});

test('comparator: name sorts alphabetically in the requested direction', () => {
  const cmp = comparator('name', 'asc');
  assert.ok(cmp({ name: 'a' }, { name: 'b' }) < 0);
  const cmpDesc = comparator('name', 'desc');
  assert.ok(cmpDesc({ name: 'a' }, { name: 'b' }) > 0);
});

test('comparator: numeric columns fall back to name as a tiebreaker', () => {
  const cmp = comparator('violations', 'desc');
  const a = { name: 'b', violations: 5, severity: {}, complianceRate: 0 };
  const b = { name: 'a', violations: 5, severity: {}, complianceRate: 0 };
  assert.ok(cmp(a, b) > 0); // equal violations -> 'b'.localeCompare('a') > 0
});

// ---------------------------------------------------------------------------
// flattenAndSort — non-mutating groups sort
// ---------------------------------------------------------------------------

test('flattenAndSort: does not mutate the input groups array order', () => {
  const groups = [
    { dimRow: { name: 'z', violations: 1, severity: {}, complianceRate: 0 }, principles: [] },
    { dimRow: { name: 'a', violations: 1, severity: {}, complianceRate: 0 }, principles: [] },
  ];
  const before = groups.map((g) => g.dimRow.name);
  flattenAndSort(groups, 'name', 'asc');
  assert.deepEqual(groups.map((g) => g.dimRow.name), before); // caller's array untouched
});

test('flattenAndSort: interleaves each dimension row with its sorted principle rows', () => {
  const groups = [
    {
      dimRow: { name: 'security', violations: 2, severity: {}, complianceRate: 0 },
      principles: [
        { name: 'Input', violations: 1, severity: {}, complianceRate: 0 },
        { name: 'Auth', violations: 1, severity: {}, complianceRate: 0 },
      ],
    },
  ];
  const rows = flattenAndSort(groups, 'name', 'asc');
  assert.deepEqual(rows.map((r) => r.name), ['security', 'Auth', 'Input']);
});

// ---------------------------------------------------------------------------
// buildRows
// ---------------------------------------------------------------------------

test('buildRows: filters out empty dimensions and sorts by the requested column', () => {
  const dims = [
    { dimension: 'empty', violations: [], compliance: [] },
    { dimension: 'security', violations: [{ principle: 'Auth', severity: 'critical' }], compliance: [] },
  ];
  const rows = buildRows(dims, 'violations', 'desc');
  assert.equal(rows.length, 2); // dimension row + 1 principle row; 'empty' dropped
  assert.equal(rows[0].type, 'dimension');
  assert.equal(rows[0].name, 'security');
});
