import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  buildRow,
  buildDimensionsBoard,
  buildAttention,
  buildDimensionView,
  buildDuelView,
} from './compareModel.js';
import { NOW, iso, makeSummary, makeProject, DIM_SEC, DIM_USE } from './_compareModel.fixtures.js';

/**
 * Split from compareModel.test.js: the dimensions board, attention strip,
 * per-dimension standings, and the head-to-head duel view.
 */

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
