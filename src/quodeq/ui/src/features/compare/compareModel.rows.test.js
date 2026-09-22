import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildRow, consequenceOf, consequenceLevel, sortRows, buildFleet } from './compareModel.js';
import { NOW, makeSummary, makeProject } from './_compareModel.fixtures.js';

/**
 * Split from compareModel.test.js: row-building, consequence scoring,
 * sorting, and fleet aggregation.
 */

test('buildRow joins project metadata with the summary payload', () => {
  const row = buildRow(
    makeProject(),
    makeSummary({
      dims: [{
        dimension: 'Security',
        overallScore: '6.5/10',
        overallGrade: 'Adequate',
        totals: { violationCount: 4, severity: { critical: 1, major: 1, minor: 2 } },
        principles: [{ principle: 'Integrity', score: '6.0' }],
      }],
    }),
    NOW,
  );
  assert.equal(row.lang, 'py');
  assert.equal(row.score, 7);
  assert.equal(row.coveragePct, 90);
  assert.equal(row.stale, false);
  assert.equal(row.dims.length, 1);
  assert.equal(row.dims[0].key, 'security');
  assert.equal(row.dims[0].score, 6.5);
  assert.equal(row.dims[0].principles[0].score, 6);
});

test('buildRow marks stale when the last run is older than a week', () => {
  const row = buildRow(makeProject(), makeSummary({ lastRunDaysAgo: 9 }), NOW);
  assert.equal(row.stale, true);
});

test('staleness follows commits-since-scan when the backend knows it', () => {
  // Old run but the code never moved -> the grade is still current.
  const untouched = buildRow(
    makeProject(),
    { ...makeSummary({ lastRunDaysAgo: 30 }), commitsSinceLastRun: 0 },
    NOW,
  );
  assert.equal(untouched.stale, false);
  // Fresh run but the code moved since -> provisional.
  const moved = buildRow(
    makeProject(),
    { ...makeSummary({ lastRunDaysAgo: 1 }), commitsSinceLastRun: 12 },
    NOW,
  );
  assert.equal(moved.stale, true);
  assert.equal(moved.commitsSince, 12);
});

test('buildRow with no summary yet is unloaded but keeps identity', () => {
  const row = buildRow(makeProject(), undefined, NOW);
  assert.equal(row.loaded, false);
  assert.equal(row.hasData, false);
  assert.equal(row.name, 'proj-one');
});

test('consequence grows with worse score, size and staleness', () => {
  const base = buildRow(makeProject(), makeSummary({ score: 5 }), NOW);
  const better = buildRow(makeProject(), makeSummary({ score: 8 }), NOW);
  const stale = buildRow(makeProject(), makeSummary({ score: 5, lastRunDaysAgo: 30 }), NOW);
  assert.ok(consequenceOf(base) > consequenceOf(better));
  assert.ok(consequenceOf(stale) > consequenceOf(base));
  assert.equal(consequenceOf(buildRow(makeProject(), undefined, NOW)), 0);
});

test('consequenceLevel thresholds are ordered', () => {
  assert.equal(consequenceLevel(25), 'severe');
  assert.equal(consequenceLevel(13), 'elevated');
  assert.equal(consequenceLevel(7), 'watch');
  assert.equal(consequenceLevel(1), 'clear');
});

test('sortRows ranks by score both directions, unscored always last', () => {
  const a = buildRow(makeProject({ id: 'a' }), makeSummary({ score: 6 }), NOW);
  const b = buildRow(makeProject({ id: 'b' }), makeSummary({ score: 9 }), NOW);
  const c = buildRow(makeProject({ id: 'c' }), undefined, NOW);
  assert.deepEqual(sortRows([a, c, b]).map((r) => r.id), ['b', 'a', 'c']);
  assert.deepEqual(sortRows([a, c, b], 'asc').map((r) => r.id), ['a', 'b', 'c']);
});

test('buildFleet aggregates severity, compliance and coverage', () => {
  const rows = [
    buildRow(makeProject({ id: 'a' }), makeSummary({ score: 6 }), NOW),
    buildRow(makeProject({ id: 'b' }), makeSummary({ score: 8 }), NOW),
  ];
  const fleet = buildFleet(rows);
  assert.equal(fleet.score, 7);
  assert.equal(fleet.severity.critical, 2);
  assert.equal(fleet.totalViolations, 20);
  assert.equal(fleet.passPct, 90);
  assert.equal(fleet.coveragePct, 90);
  assert.equal(fleet.staleCount, 0);
  // Fleet spread: best minus worst scored project.
  assert.equal(fleet.spread, 2);
  assert.equal(fleet.lead.id, 'b');
  assert.equal(fleet.trail.id, 'a');
});
