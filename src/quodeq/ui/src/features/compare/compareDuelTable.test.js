import test from 'node:test';
import assert from 'node:assert/strict';
import { TABLE_SORT, dimensionTally, scoreAxis, scoreAxisFor, sortScoreRows } from './compareDuelTable.js';

const TIERS = [[9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor']];
const dim = (label, a, b) => ({ key: label, label, a, b, gap: a != null && b != null ? Math.round((a - b) * 10) / 10 : null, shared: a != null && b != null });

test('sortScoreRows: gap size first, one-sided rows last, ties by name', () => {
  const rows = [dim('b', 7, 7.5), dim('a', 7, 6.5), dim('c', 8, 5), dim('d', 6, null)];
  assert.deepEqual(sortScoreRows(rows, TABLE_SORT.GAP).map((r) => r.label), ['c', 'a', 'b', 'd']);
});

test('sortScoreRows: by either side, missing scores last', () => {
  const rows = [dim('x', 6, 9), dim('y', 8, null), dim('z', null, 7)];
  assert.deepEqual(sortScoreRows(rows, TABLE_SORT.A).map((r) => r.label), ['y', 'x', 'z']);
  assert.deepEqual(sortScoreRows(rows, TABLE_SORT.B).map((r) => r.label), ['x', 'z', 'y']);
  assert.deepEqual(sortScoreRows(rows, TABLE_SORT.NAME).map((r) => r.label), ['x', 'y', 'z']);
});

test('scoreAxis: zooms to just under the lowest score and keeps the zones inside it', () => {
  const duel = { dimensions: [dim('s', 5.3, 7)], principles: [{ items: [{ a: 5.1, b: 9.2 }] }] };
  const axis = scoreAxis(duel, TIERS);
  assert.equal(axis.lo, 4);
  assert.deepEqual(axis.ticks, [4, 5, 6, 7, 8, 9, 10]);
  assert.deepEqual(axis.zones.map((z) => [z.label, z.from, z.to]), [['Poor', 4, 5], ['Adequate', 5, 7], ['Good', 7, 9], ['Exemplary', 9, 10]]);
  assert.equal(axis.at(4), 0);
  assert.equal(axis.at(10), 100);
});

test('scoreAxisFor: the top fits the highest score the way the bottom fits the lowest', () => {
  const axis = scoreAxisFor([8.3, 6.9, 6.8], TIERS);
  assert.deepEqual([axis.lo, axis.hi], [6, 9]);
  assert.deepEqual(axis.ticks, [6, 7, 8, 9]);
  assert.deepEqual(axis.zones.map((z) => [z.label, z.from, z.to]), [['Adequate', 6, 7], ['Good', 7, 9]]);
  assert.equal(axis.at(9), 100);
});

test('scoreAxisFor: never runs past 10, and an empty list spans the whole scale', () => {
  assert.equal(scoreAxisFor([9.8], TIERS).hi, 10);
  assert.deepEqual([scoreAxisFor([], TIERS).lo, scoreAxisFor([], TIERS).hi], [0, 10]);
});

test('scoreAxis: a wide span ticks every other point', () => {
  const axis = scoreAxis({ dimensions: [dim('s', 1.2, 9)], principles: [] }, TIERS);
  assert.equal(axis.lo, 0);
  assert.deepEqual(axis.ticks, [0, 2, 4, 6, 8, 10]);
});

test('dimensionTally: leads per side, even band, widest gap either way', () => {
  const tally = dimensionTally({ dimensions: [dim('s', 5.3, 7), dim('p', 6.7, 8), dim('u', 8.5, 8.3), dim('x', 7, null)] });
  assert.deepEqual({ ...tally, widest: tally.widest.label }, { total: 3, a: 0, b: 2, even: 1, widest: 's' });
});
