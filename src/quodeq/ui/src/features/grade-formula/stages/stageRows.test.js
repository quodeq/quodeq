import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stageRows, stageSummary } from './stageRows.js';

const stages = { types: { critical: 0, major: 1, minor: 3 }, complianceTypes: 4, weightedViolations: 2.25, base: 7.87, lift: 0.36, raw: 8.64, ceiling: 9.16, floor: 5, final: 8.6, grade: 'Good' };

test('stageRows lists the stages in scoring order with their values', () => {
  const rows = stageRows(stages);
  assert.deepEqual(rows.map((r) => r.key), ['types', 'base', 'lift', 'raw', 'ceiling', 'floor', 'final']);
  assert.equal(rows[0].value, '0 critical, 1 major, 3 minor = 2.25');
  assert.equal(rows[1].value, '7.9');
  assert.equal(rows[2].value, '4 compliance types lift 0.36 of the gap');
  assert.equal(rows[6].value, '8.6 Good');
});

test('stageSummary of an insufficient principle has no rows and no final', () => {
  const summary = stageSummary({ principleId: 'P1', insufficient: true, stages: null });
  assert.equal(summary.insufficient, true);
  assert.equal(summary.rows, null);
  assert.equal(summary.final, null);
});

test('stageSummary of a graded principle carries the seven rows and the final score with its grade', () => {
  const summary = stageSummary({ principleId: 'P1', insufficient: false, stages });
  assert.equal(summary.insufficient, false);
  assert.equal(summary.rows.length, 7);
  assert.equal(summary.final, '8.6 Good');
});
