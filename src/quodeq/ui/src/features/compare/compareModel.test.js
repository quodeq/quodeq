import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseScore10,
  nameKey,
  applyVisibleStandards,
  trendDelta,
  buildRow,
  consequenceOf,
  consequenceLevel,
  sortRows,
  buildFleet,
  buildDimensionsBoard,
  buildAttention,
  buildDimensionView,
  buildDuelView,
} from './compareModel.js';

const NOW = '2026-08-25T12:00:00Z';

const iso = (daysAgo) => new Date(Date.parse(NOW) - daysAgo * 86400000).toISOString();

function makeSummary({ score = 7, dims = [], trend = [], lastRunDaysAgo = 1 } = {}) {
  return {
    summary: {
      numericAverage: score,
      overallGrade: 'Good',
      totalViolations: 10,
      totalCompliance: 90,
      severity: { critical: 1, major: 3, minor: 6 },
    },
    dimensions: dims,
    trend,
    runsCount: trend.length || 1,
    lastRun: { runId: 'r1', dateISO: iso(lastRunDaysAgo), status: 'complete' },
  };
}

function makeProject(overrides = {}) {
  return {
    id: 'p1',
    name: 'proj-one',
    displayName: 'proj-one',
    languageStats: { py: 300, js: 40 },
    totalFiles: 500,
    analyzedFiles: 450,
    runsCount: 3,
    latestDate: iso(1),
    ...overrides,
  };
}

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

const DIM_SEC = (score) => ({
  dimension: 'Security',
  overallScore: `${score}/10`,
  totals: { violationCount: 2, severity: { critical: 0, major: 1, minor: 1 } },
  principles: [
    { principle: 'Integrity', score: `${score}` },
    { principle: 'Confidentiality', score: `${Math.max(1, score - 1)}` },
  ],
});

test('buildDimensionsBoard unions dimensions across projects', () => {
  const rows = [
    buildRow(makeProject({ id: 'a' }), makeSummary({ dims: [DIM_SEC(6)] }), NOW),
    buildRow(
      makeProject({ id: 'b' }),
      makeSummary({ dims: [DIM_SEC(8), { dimension: 'Usability', overallScore: '7/10', totals: { violationCount: 1, severity: {} }, principles: [] }] }),
      NOW,
    ),
  ];
  const board = buildDimensionsBoard(rows, NOW, {});
  assert.deepEqual(board.map((b) => b.key), ['security', 'usability']);
  const sec = board[0];
  assert.equal(sec.avg, 7);
  assert.equal(sec.violations, 4);
  assert.deepEqual(sec.perProject.map((p) => p.id), ['b', 'a']);
});

test('buildAttention surfaces reasons for the riskiest projects', () => {
  const risky = buildRow(
    makeProject({ id: 'bad', totalFiles: 3000, analyzedFiles: 1500 }),
    makeSummary({ score: 4.2, dims: [DIM_SEC(3.9)], lastRunDaysAgo: 10 }),
    NOW,
  );
  const fine = buildRow(makeProject({ id: 'ok' }), makeSummary({ score: 8.8, dims: [DIM_SEC(8.8)] }), NOW);
  const [first] = buildAttention([fine, risky]);
  assert.equal(first.row.id, 'bad');
  const types = first.reasons.map((r) => r.type);
  assert.ok(types.includes('worstDim'));
  assert.ok(types.includes('stale'));
  assert.ok(types.includes('coverage'));
  assert.equal(first.worstDim, 'security');
});

test('buildAttention returns every scored row, worst first — the view caps the strip', () => {
  const rows = [8.8, 4.2, 6.1, 7.5, 5.0].map((score, i) => buildRow(
    makeProject({ id: `p${i}` }),
    makeSummary({ score, dims: [DIM_SEC(score)] }),
    NOW,
  ));
  const attention = buildAttention(rows);
  assert.equal(attention.length, rows.length);
  const values = attention.map((a) => a.value);
  assert.deepEqual(values, values.slice().sort((a, b) => b - a));
});

test('buildDimensionView ranks standings and aggregates principles', () => {
  const summaries = {
    a: makeSummary({ dims: [DIM_SEC(6)] }),
    b: makeSummary({ dims: [DIM_SEC(8)] }),
  };
  const rows = [
    buildRow(makeProject({ id: 'a' }), summaries.a, NOW),
    buildRow(makeProject({ id: 'b' }), summaries.b, NOW),
  ];
  const view = buildDimensionView('security', rows, NOW, summaries);
  assert.equal(view.lead.row.id, 'b');
  assert.equal(view.trail.row.id, 'a');
  assert.equal(view.spread, 2);
  assert.deepEqual(view.principles.map((p) => p.key), ['confidentiality', 'integrity']);
  const integ = view.principles.find((p) => p.key === 'integrity');
  assert.equal(integ.avg, 7);
  assert.equal(integ.lead.id, 'b');
  assert.equal(integ.trail.id, 'a');
  // Bars follow the standings order and carry the standings rank, so the
  // same slot is the same project in every principle card.
  assert.deepEqual(integ.perProject.map((p) => [p.id, p.rank]), [['b', 1], ['a', 2]]);
  assert.equal(view.weakest.key, 'confidentiality');
});

test('buildDimensionView returns null for a dimension nobody has', () => {
  const rows = [buildRow(makeProject(), makeSummary({ dims: [DIM_SEC(6)] }), NOW)];
  assert.equal(buildDimensionView('reliability', rows, NOW, {}), null);
});

const DIM_USE = (score) => ({
  dimension: 'Usability',
  overallScore: `${score}/10`,
  totals: { violationCount: 1, severity: { critical: 0, major: 0, minor: 1 } },
  principles: [{ principle: 'Clarity', score: `${score}` }],
});

function makeDuel({ dimsA = [DIM_SEC(6)], dimsB = [DIM_SEC(8)], trendA = [], trendB = [] } = {}) {
  const summaries = {
    a: makeSummary({ score: 6, dims: dimsA, trend: trendA }),
    b: makeSummary({ score: 8, dims: dimsB, trend: trendB }),
  };
  const rows = [
    buildRow(makeProject({ id: 'a', displayName: 'proj-a' }), summaries.a, NOW),
    buildRow(makeProject({ id: 'b', displayName: 'proj-b' }), summaries.b, NOW),
  ];
  return { rows, summaries };
}

test('buildDuelView returns null unless both projects are in the rows', () => {
  const { rows, summaries } = makeDuel();
  assert.equal(buildDuelView('a', 'missing', rows, NOW, summaries), null);
  assert.equal(buildDuelView('missing', 'b', rows, NOW, summaries), null);
});

test('buildDuelView reports the overall gap as left minus right', () => {
  const { rows, summaries } = makeDuel();
  const duel = buildDuelView('a', 'b', rows, NOW, summaries);
  assert.equal(duel.a.id, 'a');
  assert.equal(duel.b.id, 'b');
  assert.equal(duel.gap, -2);
  assert.equal(duel.ready, true);
});

test('buildDuelView is not ready while either side lacks a score', () => {
  const { summaries } = makeDuel();
  const rows = [
    buildRow(makeProject({ id: 'a' }), summaries.a, NOW),
    buildRow(makeProject({ id: 'b' }), undefined, NOW),
  ];
  const duel = buildDuelView('a', 'b', rows, NOW, { a: summaries.a });
  assert.equal(duel.ready, false);
  assert.equal(duel.gap, null);
});

test('buildDuelView unions dimensions alphabetically and gaps only shared ones', () => {
  const { rows, summaries } = makeDuel({
    dimsA: [DIM_SEC(6)],
    dimsB: [DIM_SEC(8), DIM_USE(7)],
  });
  const duel = buildDuelView('a', 'b', rows, NOW, summaries);
  assert.deepEqual(duel.dimensions.map((d) => d.key), ['security', 'usability']);
  const [sec, use] = duel.dimensions;
  assert.equal(sec.a, 6);
  assert.equal(sec.b, 8);
  assert.equal(sec.gap, -2);
  assert.equal(sec.shared, true);
  assert.equal(use.a, null);
  assert.equal(use.b, 7);
  assert.equal(use.gap, null);
  assert.equal(use.shared, false);
  assert.equal(duel.sharedCount, 1);
});

test('buildDuelView diffs principles only for shared dimensions', () => {
  const { rows, summaries } = makeDuel({
    dimsA: [DIM_SEC(6)],
    dimsB: [DIM_SEC(8), DIM_USE(7)],
  });
  const duel = buildDuelView('a', 'b', rows, NOW, summaries);
  // Usability is one-sided, so no principle group for it.
  assert.deepEqual(duel.principles.map((g) => g.key), ['security']);
  const items = duel.principles[0].items;
  assert.deepEqual(items.map((i) => i.key), ['confidentiality', 'integrity']);
  const integ = items.find((i) => i.key === 'integrity');
  assert.equal(integ.a, 6);
  assert.equal(integ.b, 8);
  assert.equal(integ.gap, -2);
});

test('buildDuelView keeps a one-sided principle inside a shared dimension, gapless', () => {
  const withExtra = DIM_SEC(8);
  withExtra.principles = withExtra.principles.concat([{ principle: 'Traceability', score: '7' }]);
  const { rows, summaries } = makeDuel({ dimsA: [DIM_SEC(6)], dimsB: [withExtra] });
  const duel = buildDuelView('a', 'b', rows, NOW, summaries);
  const trace = duel.principles[0].items.find((i) => i.key === 'traceability');
  assert.equal(trace.a, null);
  assert.equal(trace.b, 7);
  assert.equal(trace.gap, null);
});

test('buildDuelView extracts both trend series sorted by date', () => {
  const { rows, summaries } = makeDuel({
    trendA: [
      { dateISO: iso(1), numericAverage: 6.0 },
      { dateISO: iso(30), numericAverage: 5.5 },
    ],
    trendB: [{ dateISO: iso(10), numericAverage: 7.9 }],
  });
  const duel = buildDuelView('a', 'b', rows, NOW, summaries);
  assert.deepEqual(duel.trend.a.map((e) => e.value), [5.5, 6.0]);
  assert.deepEqual(duel.trend.b.map((e) => e.value), [7.9]);
  assert.equal(duel.trend.a[0].dateISO, iso(30));
});
