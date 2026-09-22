import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseScore10, nameKey, applyVisibleStandards, trendDelta } from './compareModel.js';
import { NOW, iso } from './_compareModel.fixtures.js';

/**
 * Split from compareModel.test.js: score parsing, name normalization,
 * trend deltas, and standards-visibility filtering.
 */

test('parseScore10 handles numbers and score strings', () => {
  assert.equal(parseScore10(7.2), 7.2);
  assert.equal(parseScore10('7.2'), 7.2);
  assert.equal(parseScore10('7.2/10'), 7.2);
  assert.equal(parseScore10('7.2/10 Good'), 7.2);
  assert.equal(parseScore10(null), null);
  assert.equal(parseScore10('N/A'), null);
});

test('nameKey normalizes case and whitespace', () => {
  assert.equal(nameKey(' Security '), 'security');
  assert.equal(nameKey('security'), nameKey('Security'));
});

test('trendDelta uses the newest run at or before the window start as baseline', () => {
  const trend = [
    { dateISO: iso(80), numericAverage: 6.0 },
    { dateISO: iso(56), numericAverage: 6.4 }, // newest at/before the 30d window start -> baseline
    { dateISO: iso(20), numericAverage: 6.9 },
    { dateISO: iso(1), numericAverage: 7.1 },
  ];
  const { delta, lastDelta, spark } = trendDelta(trend, NOW);
  assert.equal(delta, 0.7);
  assert.equal(lastDelta, 0.2); // latest minus previous run
  assert.deepEqual(spark, [6.0, 6.4, 6.9, 7.1]);
});

test('trendDelta still reports lastDelta when every run predates the window', () => {
  const trend = [
    { dateISO: iso(120), numericAverage: 6.0 },
    { dateISO: iso(90), numericAverage: 6.6 },
  ];
  const { delta, lastDelta } = trendDelta(trend, NOW);
  assert.equal(delta, null); // nothing moved within the window
  assert.equal(lastDelta, 0.6);
});

test('trendDelta falls back to the oldest entry when all runs are inside the window', () => {
  const trend = [
    { dateISO: iso(10), numericAverage: 6.0 },
    { dateISO: iso(1), numericAverage: 6.5 },
  ];
  assert.equal(trendDelta(trend, NOW).delta, 0.5);
});

test('trendDelta needs two entries', () => {
  assert.equal(trendDelta([{ dateISO: iso(1), numericAverage: 7 }], NOW).delta, null);
  assert.equal(trendDelta([], NOW).delta, null);
});

test('applyVisibleStandards hides disabled dimensions and recomputes the summary', () => {
  const summary = {
    summary: {
      numericAverage: 7,
      totalViolations: 10,
      totalCompliance: 90,
      severity: { critical: 2, major: 3, minor: 5 },
    },
    dimensions: [
      { dimension: 'Security', overallScore: '6.0/10', totals: { violationCount: 4, complianceCount: 40, severity: { critical: 2, major: 1, minor: 1 } } },
      { dimension: 'Usability', overallScore: '8.0/10', totals: { violationCount: 6, complianceCount: 50, severity: { critical: 0, major: 2, minor: 4 } } },
    ],
    trend: [
      { runId: 'r1', dateISO: iso(1), numericAverage: 7, dimensionDetails: [
        { dimension: 'Security', score: 6 }, { dimension: 'Usability', score: 8 },
      ] },
    ],
  };
  const filtered = applyVisibleStandards(summary, ['security']);
  assert.deepEqual(filtered.dimensions.map((d) => d.dimension), ['Security']);
  assert.equal(filtered.summary.totalViolations, 4);
  assert.equal(filtered.summary.totalCompliance, 40);
  assert.equal(filtered.summary.severity.critical, 2);
  // Trend average recomputed over the visible dimension only.
  assert.equal(filtered.trend[0].numericAverage, 6);
  assert.deepEqual(filtered.trend[0].dimensionDetails.map((d) => d.dimension), ['Security']);
});

test('applyVisibleStandards passes through when nothing is hidden or ids are absent', () => {
  const summary = {
    summary: { numericAverage: 7 },
    dimensions: [{ dimension: 'Security', totals: { violationCount: 1, complianceCount: 1, severity: {} } }],
    trend: [],
  };
  assert.equal(applyVisibleStandards(summary, ['security']), summary);
  assert.equal(applyVisibleStandards(summary, null), summary);
});
