import test from 'node:test';
import assert from 'node:assert/strict';
import { dimensionKpis, dimensionRows, principleHealth } from './compareDimensionOverview.js';

const TIERS = [[9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor']];
const project = (id, files) => ({ id, name: id, totalFiles: files, analyzedFiles: null });
const VIEW = {
  avg: 7.5, delta: 0.4, spread: 2,
  standings: [
    { row: project('a', 900), score: 8.5, delta: 0.6, lastDelta: 0.6, violations: 9, compliance: 91, severity: { critical: 9 },
      principles: [{ key: 'inst', label: 'installability', name: 'Installability', score: 9 }, { key: 'adap', label: 'adaptability', name: 'Adaptability', score: 8 }] },
    { row: project('b', 100), score: 6.5, delta: null, lastDelta: null, violations: 11, compliance: 89, severity: { critical: 1 },
      principles: [{ key: 'inst', label: 'installability', name: 'Installability', score: null }, { key: 'adap', label: 'adaptability', name: 'Adaptability', score: 5 }] },
  ],
  principles: [
    { key: 'adap', label: 'adaptability', avg: 6.5, lead: { id: 'a', name: 'a', score: 8 }, perProject: [{ id: 'a', name: 'a', score: 8 }, { id: 'b', name: 'b', score: 5 }] },
    { key: 'inst', label: 'installability', avg: 9, lead: { id: 'a', name: 'a', score: 9 }, perProject: [{ id: 'a', name: 'a', score: 9 }] },
  ],
};
VIEW.lead = VIEW.standings[0];
VIEW.trail = VIEW.standings[1];

test('dimensionRows: the score, violations and severity are the dimension’s; principles become cells with nav targets', () => {
  const rows = dimensionRows(VIEW);
  assert.deepEqual(rows.map((r) => [r.id, r.score, r.totalViolations]), [['a', 8.5, 9], ['b', 6.5, 11]]);
  assert.deepEqual(rows[1].dims.map((d) => d.key), ['adap']);
  assert.deepEqual(rows[0].dims[1].cell, { id: 'a', name: 'a', score: 8 });
});

test('dimensionKpis: below good, coverage against the scope, densities per file', () => {
  const k = dimensionKpis(VIEW, dimensionRows(VIEW), 5, 7);
  assert.equal(k.below, 1);
  assert.deepEqual([k.projects, k.scope], [2, 5]);
  assert.equal(k.density, 2);
  assert.equal(k.criticalPerK, 10);
});

test('principleHealth: weakest first, coverage of the dimension’s projects, leader and trailer', () => {
  const [adap, inst] = principleHealth(VIEW, TIERS);
  assert.equal(adap.key, 'adap');
  assert.deepEqual([adap.total, adap.of, adap.below], [2, 2, 1]);
  assert.equal(adap.lead.name, 'a');
  assert.equal(adap.trail.name, 'b');
  assert.deepEqual([inst.total, inst.of], [1, 2]);
});
