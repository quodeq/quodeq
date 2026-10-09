import { test } from 'node:test';
import assert from 'node:assert/strict';
import { stageRows, stageSummary } from './stageRows.js';

const stages = { violationRules: 2, complianceRules: 1, violationMass: 6.4, complianceMass: 2.6, observation: 9.3, requirements: [], compliance: [], base: 6.6, lift: 0.1, raw: 6.9, ceiling: 8.6, floor: 0, final: 6.9, grade: 'Adequate' };

test('stageRows lists the stages in scoring order with their values', () => {
  const rows = stageRows(stages);
  assert.deepEqual(rows.map((r) => r.key), ['rules', 'base', 'lift', 'raw', 'ceiling', 'floor', 'final']);
  assert.equal(rows[0].value, '2 rules weigh 6.40');
  assert.equal(rows[1].value, '6.6');
  assert.equal(rows[2].value, '1 compliance rule(s) lift 0.10 of the gap');
  assert.equal(rows[6].value, '6.9 Adequate');
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
  assert.equal(summary.final, '6.9 Adequate');
});
