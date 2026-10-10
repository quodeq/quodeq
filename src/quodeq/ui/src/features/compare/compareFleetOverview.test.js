import test from 'node:test';
import assert from 'node:assert/strict';
import { FLEET_SORT, LOWEST_TIER_LABEL, dimensionHealth, fleetKpis, sortFleet } from './compareFleetOverview.js';

const TIERS = [[9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor']];
const row = (over) => ({
  name: 'p', score: 7, delta: null, totalFiles: 100, analyzedFiles: null, totalViolations: 50, totalCompliance: 50,
  severity: { critical: 1 }, lastISO: '2026-10-01T00:00:00Z', stale: false, ...over,
});

test('fleetKpis: size-weighted score, densities per analysed (or total) files, freshness', () => {
  const rows = [row({ name: 'big', score: 6, totalFiles: 900, totalViolations: 90, severity: { critical: 9 } }),
    row({ name: 'small', score: 10, totalFiles: 100, totalViolations: 10, severity: { critical: 1 }, stale: true })];
  const k = fleetKpis(rows, { score: 8, delta: 0.5, spread: 4, lead: rows[1], trail: rows[0] });
  assert.equal(k.weighted, 6.4);
  assert.equal(k.files, 1000);
  assert.equal(k.density, 10);
  assert.equal(k.critical, 10);
  assert.equal(k.criticalPerK, 10);
  assert.deepEqual([k.fresh, k.stale], [1, 1]);
  assert.equal(k.coverage, null);
});

test('sortFleet: best first per column, reversed on request, missing values always last', () => {
  const rows = [row({ name: 'a', delta: 0.4 }), row({ name: 'b', delta: null }), row({ name: 'c', delta: -0.2 })];
  assert.deepEqual(sortFleet(rows, FLEET_SORT.MOVE).map((r) => r.name), ['a', 'c', 'b']);
  assert.deepEqual(sortFleet(rows, FLEET_SORT.MOVE, false).map((r) => r.name), ['c', 'a', 'b']);
});

test('sortFleet: density and criticals rank the cleanest first', () => {
  const rows = [row({ name: 'dirty', totalViolations: 90 }), row({ name: 'clean', totalViolations: 5 })];
  assert.deepEqual(sortFleet(rows, FLEET_SORT.DENSITY).map((r) => r.name), ['clean', 'dirty']);
  const crit = [row({ name: 'many', severity: { critical: 9 } }), row({ name: 'none', severity: { critical: 0 } })];
  assert.deepEqual(sortFleet(crit, FLEET_SORT.CRITICAL).map((r) => r.name), ['none', 'many']);
});

test('sortFleet: ties keep name order', () => {
  const rows = [row({ name: 'z' }), row({ name: 'a' })];
  assert.deepEqual(sortFleet(rows, FLEET_SORT.SCORE).map((r) => r.name), ['a', 'z']);
});

test('dimensionHealth: weakest first, grade mix best tier first, below-good and weakest project', () => {
  const p = (name, score) => ({ id: name, name, score });
  const board = [
    { key: 'ux', label: 'usability', avg: 8.7, delta: 0.3, violations: 10, perProject: [p('a', 9.2), p('b', 8.1)] },
    { key: 'sec', label: 'security', avg: 6, delta: null, violations: 30, perProject: [p('a', 9.5), p('b', 6.2), p('c', 2.1), p('d', null)] },
  ];
  const [sec, ux] = dimensionHealth(board, TIERS);
  assert.equal(sec.key, 'sec');
  assert.deepEqual(sec.mix, [{ label: 'Exemplary', count: 1 }, { label: 'Adequate', count: 1 }, { label: LOWEST_TIER_LABEL, count: 1 }]);
  assert.deepEqual([sec.total, sec.below, sec.weakest.name], [3, 2, 'c']);
  assert.equal(ux.below, 0);
});
