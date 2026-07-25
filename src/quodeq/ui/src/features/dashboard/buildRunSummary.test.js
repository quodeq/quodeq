import test from 'node:test';
import assert from 'node:assert/strict';
import buildRunSummary from './buildRunSummary.js';

const dim = (over = {}) => ({
  dimension: 'maintainability',
  overallGrade: 'Fair',
  overallScore: '6.0',
  totals: {
    violationCount: 1,
    complianceCount: 2,
    severity: { critical: 0, major: 1, minor: 0 },
  },
  ...over,
});

// ---------------------------------------------------------------------------
// dismissed aggregation
// ---------------------------------------------------------------------------

test('dismissed: sums dismissedCount across dimensions', () => {
  const summary = buildRunSummary([
    dim({ dismissedCount: 3 }),
    dim({ dimension: 'security', dismissedCount: 2 }),
  ]);
  assert.equal(summary.dismissed, 5);
});

test('dismissed: 0 when no dimension carries dismissedCount', () => {
  const summary = buildRunSummary([dim(), dim({ dimension: 'security' })]);
  assert.equal(summary.dismissed, 0);
});

test('dismissed: 0 for the empty-dimensions fallback', () => {
  const summary = buildRunSummary([]);
  assert.equal(summary.dismissed, 0);
});

test('dismissed: ignores non-numeric dismissedCount', () => {
  const summary = buildRunSummary([dim({ dismissedCount: 'nope' })]);
  assert.equal(summary.dismissed, 0);
});

// ---------------------------------------------------------------------------
// suppressed aggregation (dismissed + deleted)
// ---------------------------------------------------------------------------

test('suppressed: sums suppressedCount across dimensions', () => {
  const summary = buildRunSummary([
    dim({ dimension: 'reliability', suppressedCount: 339 }),
    dim({ dimension: 'security', suppressedCount: 52 }),
  ]);
  assert.equal(summary.suppressed, 391);
});

test('suppressed: counts deletions that dismissedCount misses', () => {
  // A project whose triage history is all deletions: dismissed reads 0 while
  // the scan still re-finds hundreds of suppressed findings every run.
  const summary = buildRunSummary([dim({ suppressedCount: 339 })]);
  assert.equal(summary.dismissed, 0);
  assert.equal(summary.suppressed, 339);
});

test('suppressed: 0 when no dimension carries suppressedCount', () => {
  assert.equal(buildRunSummary([dim()]).suppressed, 0);
});

test('suppressed: 0 for the empty-dimensions fallback', () => {
  assert.equal(buildRunSummary([]).suppressed, 0);
});

test('suppressed: ignores a non-numeric suppressedCount', () => {
  assert.equal(buildRunSummary([dim({ suppressedCount: 'nope' })]).suppressed, 0);
});

// ---------------------------------------------------------------------------
// existing aggregation still intact
// ---------------------------------------------------------------------------

test('aggregates totals and severity as before', () => {
  const summary = buildRunSummary([
    dim({ dismissedCount: 1 }),
    dim({ dimension: 'security' }),
  ]);
  assert.equal(summary.totalViolations, 2);
  assert.equal(summary.totalCompliance, 4);
  assert.equal(summary.severity.major, 2);
  assert.equal(summary.dimensionCount, 2);
});
