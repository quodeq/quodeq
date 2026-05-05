import test from 'node:test';
import assert from 'node:assert/strict';
import { buildJobStatCells, formatClock } from './buildJobStatCells.js';

const baseInputs = {
  overallPct: 62,
  takenFiles: 138,
  totalFiles: 220,
  elapsedS: 134,         // 02:14
  liveCount: 2,
};

// ---------------------------------------------------------------------------
// formatClock
// ---------------------------------------------------------------------------

test('formatClock: formats seconds as m:ss', () => {
  assert.equal(formatClock(0), '0:00');
  assert.equal(formatClock(59), '0:59');
  assert.equal(formatClock(60), '1:00');
  assert.equal(formatClock(134), '2:14');
  assert.equal(formatClock(3661), '61:01');
});

test('formatClock: returns "—" for null/undefined/non-finite', () => {
  assert.equal(formatClock(null), '—');
  assert.equal(formatClock(undefined), '—');
  assert.equal(formatClock(NaN), '—');
  assert.equal(formatClock(Infinity), '—');
});

// ---------------------------------------------------------------------------
// buildJobStatCells
// ---------------------------------------------------------------------------

test('buildJobStatCells: builds 4 cells for a running job with progress data', () => {
  const cells = buildJobStatCells('running', baseInputs);
  assert.equal(cells.length, 4);
  assert.equal(cells[0].label, 'STATUS');
  assert.equal(cells[0].value, 'running');
  assert.equal(cells[0].tone, 'warning');
  assert.equal(cells[1].label, 'PROGRESS');
  assert.equal(cells[1].value, '62%');
  assert.ok(cells[1].hint.includes('138 / 220'), `hint should contain "138 / 220", got: ${cells[1].hint}`);
  assert.equal(cells[2].label, 'FOUND');
  assert.equal(cells[2].value, 2);
  assert.equal(cells[2].tone, 'critical');
  assert.equal(cells[3].label, 'ELAPSED');
  assert.equal(cells[3].value, '2:14');
});

test('buildJobStatCells: builds done-state cells with SCANNED + VIOLATIONS + DURATION', () => {
  const cells = buildJobStatCells('done', { ...baseInputs, takenFiles: 220, liveCount: 13, elapsedS: 272 });
  assert.equal(cells[0].label, 'STATUS');
  assert.equal(cells[0].value, 'done');
  assert.equal(cells[0].tone, 'success');
  assert.equal(cells[0].hint, null);   // when violations exist, hint stays out of the way
  assert.equal(cells[1].label, 'SCANNED');
  assert.equal(cells[1].value, 220);
  assert.equal(cells[2].label, 'VIOLATIONS');
  assert.equal(cells[2].value, 13);
  assert.equal(cells[2].tone, 'critical');
  assert.equal(cells[3].label, 'DURATION');
  assert.equal(cells[3].value, '4:32');
});

test('buildJobStatCells: uses correct tone for STATUS by status', () => {
  assert.equal(buildJobStatCells('running',   baseInputs)[0].tone, 'warning');
  assert.equal(buildJobStatCells('done',      baseInputs)[0].tone, 'success');
  assert.equal(buildJobStatCells('completed', baseInputs)[0].tone, 'success');
  assert.equal(buildJobStatCells('failed',    baseInputs)[0].tone, 'critical');
  assert.equal(buildJobStatCells('lost',      baseInputs)[0].tone, 'critical');
  assert.equal(buildJobStatCells('cancelled', baseInputs)[0].tone, 'default');
});

test('buildJobStatCells: FOUND/VIOLATIONS cell tone is default when liveCount is 0', () => {
  const running = buildJobStatCells('running', { ...baseInputs, liveCount: 0 });
  const done    = buildJobStatCells('done',    { ...baseInputs, liveCount: 0 });
  assert.equal(running[2].tone, 'default');
  assert.equal(done[2].tone, 'default');
});

test('buildJobStatCells: renders "—" for missing data', () => {
  const cells = buildJobStatCells('running', {
    overallPct: 0, takenFiles: 0, totalFiles: 0, elapsedS: null, liveCount: 0,
  });
  assert.equal(cells[1].value, '—');   // PROGRESS — no data yet
  assert.equal(cells[3].value, '—');   // ELAPSED — no data yet
});

test('buildJobStatCells: failed/cancelled show PROGRESS + FOUND-so-far + ELAPSED', () => {
  const failed = buildJobStatCells('failed', baseInputs);
  assert.equal(failed[1].label, 'PROGRESS');
  assert.equal(failed[2].label, 'FOUND');
  assert.equal(failed[3].label, 'ELAPSED');
});
