import { test } from 'node:test';
import assert from 'node:assert/strict';
import { liveStages, pickPrincipleId } from './liveStages.js';
import { STAGE_STATUS } from '../../../vocab/stageStatus.js';

const stages = { types: { critical: 0, major: 1, minor: 3 }, complianceTypes: 4, weightedViolations: 2.25, base: 7.87, lift: 0.36, raw: 8.64, ceiling: 9.16, floor: 5, final: 8.6, grade: 'Good' };
const params = { severityWeight: { critical: 4, major: 1.5, minor: 0.25 }, baseK: 0.12, liftCompress: 1.8, ceilScale: 0.5, floorMinor: 8, floorMajor: 5, gradeThresholds: [[9, 'Exemplary'], [7, 'Good']] };
const principles = [
  { principleId: 'Weak', insufficient: true, stages: null },
  { principleId: 'P1', insufficient: false, stages },
];
const stored = { params, principles };
const live = { params: { ...params, baseK: 0.5 }, principles: [principles[0], { principleId: 'P1', insufficient: false, stages: { ...stages, final: 7.1 } }] };

test('pickPrincipleId keeps a known id and otherwise takes the first graded principle', () => {
  assert.equal(pickPrincipleId(principles, 'P1'), 'P1');
  assert.equal(pickPrincipleId(principles, 'nope'), 'P1');
  assert.equal(pickPrincipleId([principles[0]], null), 'Weak');
  assert.equal(pickPrincipleId([], null), null);
});

test('liveStages: no run gives the no-run note and no rows', () => {
  const out = liveStages({ stored: null, live: null, status: STAGE_STATUS.UNAVAILABLE }, null);
  assert.equal(out.stored, null);
  assert.equal(out.live, null);
  assert.match(out.note, /finished run/);
});

test('liveStages: stored rows only while the draft is not computed yet', () => {
  const out = liveStages({ stored, live: null, status: STAGE_STATUS.READY }, 'P1');
  assert.equal(out.stored.length, 7);
  assert.equal(out.live, null);
  assert.equal(out.note, null);
});

test('liveStages: stored and live rows for the picked principle', () => {
  const out = liveStages({ stored, live, status: STAGE_STATUS.READY }, 'P1');
  assert.equal(out.stored[6].value, '8.6 Good');
  assert.equal(out.live[6].value, '7.1 Good');
});

test('liveStages: an insufficient principle gives the insufficient note', () => {
  const out = liveStages({ stored, live, status: STAGE_STATUS.READY }, 'Weak');
  assert.equal(out.stored, null);
  assert.match(out.note, /Weak/);
});

test('liveStages: a run that cannot be read says so, not "no run"', () => {
  const out = liveStages({ stored: null, live: null, status: STAGE_STATUS.ERROR }, null);
  assert.match(out.note, /could not be read/);
  assert.equal(out.stored, null);
});

test('liveStages: a shared repository says the example needs a local run', () => {
  const out = liveStages({ stored: null, live: null, status: STAGE_STATUS.UNAVAILABLE }, null, { shared: true });
  assert.match(out.note, /shared/);
});
