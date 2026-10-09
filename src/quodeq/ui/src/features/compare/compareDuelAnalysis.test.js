import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DUEL_CHECK, DUEL_SIGNAL, comparabilityChecks, duelSignal, exposureOf, gapContributions, noiseOf, principleMap,
} from './compareDuelAnalysis.js';

const series = (values) => values.map((value, i) => ({ dateISO: `2026-09-${String(i + 1).padStart(2, '0')}T00:00:00Z`, value }));
const row = (over) => ({
  name: 'p', lastISO: '2026-10-01T00:00:00Z', commitsSince: 0, totalFiles: 100, lang: 'py',
  coveragePct: null, totalViolations: 10, totalCompliance: 90, analyzedFiles: 50, severity: { critical: 1, major: 2, minor: 3 },
  ...over,
});
const duelOf = (over) => ({
  a: row({ name: 'Alpha' }), b: row({ name: 'Beta' }), gap: 1, dimensions: [], sharedCount: 0, principles: [],
  trend: { a: [], b: [] }, ...over,
});

test('noiseOf: median absolute day-to-day change, null below four points', () => {
  assert.equal(noiseOf(series([7, 7.2, 7])), null);
  assert.ok(Math.abs(noiseOf(series([7, 7.4, 7.0, 7.3])) - 0.4) < 1e-9);
});

test('noiseOf: a flat history still has a noise floor', () => {
  assert.equal(noiseOf(series([7, 7, 7, 7])), 0.1);
});

test('duelSignal: unknown without enough history on either side', () => {
  assert.equal(duelSignal(duelOf({ trend: { a: series([7, 7, 7, 7]), b: [] } })).level, DUEL_SIGNAL.UNKNOWN);
});

test('duelSignal: grades the gap against the combined swing', () => {
  const trend = { a: series([7, 7.3, 7, 7.3]), b: series([6, 6.4, 6, 6.4]) }; // noise 0.3 and 0.4 -> 0.5
  assert.equal(duelSignal(duelOf({ gap: 1.2, trend })).level, DUEL_SIGNAL.CLEAR);
  assert.equal(duelSignal(duelOf({ gap: 0.7, trend })).level, DUEL_SIGNAL.PROBABLE);
  assert.equal(duelSignal(duelOf({ gap: -0.3, trend })).level, DUEL_SIGNAL.NOISE);
});

test('comparabilityChecks: unshared dimensions, distant scans and unscanned commits are cautions', () => {
  const checks = comparabilityChecks(duelOf({
    a: row({ name: 'Alpha', lastISO: '2026-08-01T00:00:00Z', commitsSince: 12 }),
    dimensions: [{ shared: true }, { shared: false }],
    sharedCount: 1,
  }));
  const byKey = (k) => checks.filter((c) => c.key === k);
  assert.equal(byKey(DUEL_CHECK.DIMENSIONS)[0].ok, false);
  assert.deepEqual(byKey(DUEL_CHECK.SCAN_GAP)[0], { key: DUEL_CHECK.SCAN_GAP, ok: false, params: { days: 61 } });
  assert.deepEqual(byKey(DUEL_CHECK.COMMITS).map((c) => c.params.name), ['Alpha']);
  assert.equal(byKey(DUEL_CHECK.SIZE)[0].ok, true);
  assert.equal(byKey(DUEL_CHECK.COVERAGE).length, 0);
});

test('comparabilityChecks: a big coverage difference is a caution', () => {
  const checks = comparabilityChecks(duelOf({ a: row({ coveragePct: 95 }), b: row({ coveragePct: 60 }) }));
  assert.equal(checks.find((c) => c.key === DUEL_CHECK.COVERAGE).ok, false);
});

test('gapContributions: shared dimensions explain (a - b) / n each, the rest is its own row', () => {
  const rows = gapContributions(duelOf({
    gap: 0.5,
    dimensions: [
      { key: 'sec', label: 'security', a: 8, b: 6, gap: 2, shared: true },
      { key: 'rel', label: 'reliability', a: 6, b: 7, gap: -1, shared: true },
      { key: 'ux', label: 'usability', a: 7, b: null, gap: null, shared: false },
    ],
  }));
  assert.deepEqual(rows.map((r) => [r.key, r.value]), [['sec', 0.7], ['rel', -0.3], ['rest', 0.2]]);
  assert.equal(rows.at(-1).rest, true);
});

test('principleMap: edges per side, even band, and shared weaknesses', () => {
  const items = [
    { key: 'p1', label: 'p1', a: 9, b: 5, gap: 4 },
    { key: 'p2', label: 'p2', a: 5, b: 8, gap: -3 },
    { key: 'p3', label: 'p3', a: 6, b: 6.2, gap: -0.2 },
    { key: 'p4', label: 'p4', a: 4, b: null, gap: null },
  ];
  const map = principleMap(duelOf({ principles: [{ key: 'sec', label: 'security', items }] }), 7);
  assert.equal(map.points.length, 3);
  assert.deepEqual(map.aEdges.map((p) => p.key), ['p1']);
  assert.deepEqual(map.bEdges.map((p) => p.key), ['p2']);
  assert.deepEqual(map.shared.map((p) => p.key), ['p3']);
  assert.deepEqual(map.counts, { a: 1, b: 1, even: 1 });
  assert.equal(map.points[0].dimLabel, 'security');
});

test('exposureOf: per 100 analysed files, falling back to total files', () => {
  assert.equal(exposureOf(row({})).per100, 20);
  assert.equal(exposureOf(row({ analyzedFiles: null })).per100, 10);
  assert.equal(exposureOf(row({ totalViolations: 0, totalCompliance: 0 })).passPct, null);
  assert.equal(exposureOf(row({})).passPct, 90);
});

test('duelSignal: the level follows the rounded ratio the reader sees', () => {
  // noise 0.3 and 0.4 -> 0.5; 1.0 / 0.5 is 1.9999... in floating point.
  const trend = { a: series([7, 7.3, 7, 7.3, 7.5]), b: series([6, 6.4, 6, 6.4, 6.5]) };
  const signal = duelSignal(duelOf({ gap: 1, trend }));
  assert.equal(signal.ratio, 2);
  assert.equal(signal.level, DUEL_SIGNAL.CLEAR);
});
