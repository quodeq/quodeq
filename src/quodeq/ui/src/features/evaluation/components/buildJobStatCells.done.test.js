import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildJobStatCells } from './buildJobStatCells.js';

// A finished run's tiles say the same things the running tiles said, settled:
// dimensions done, files this run, new violations, and the time against the
// run's budget. The header already says the run is complete.
const base = {
  takenFiles: 265, totalFiles: 265, overallPct: 100, elapsedS: 328, liveCount: 1,
  sevCounts: { critical: 0, major: 0, minor: 1 }, suppressedCount: 43, carriedCount: 1,
  scanMode: 'incremental', budgetS: 600, dimsDone: 7, dimsTotal: 7,
};

test('done tiles: dimensions, files this run, new violations, duration of the budget', () => {
  const [dims, files, found, duration] = buildJobStatCells('done', base);
  assert.deepEqual([dims.label, dims.value, dims.trailing, dims.hint], ['dimensions', 7, '/ 7', 'all done']);
  assert.deepEqual([files.label, files.value, files.trailing, files.hint], ['files this run', 265, '/ 265', 'changed files']);
  assert.deepEqual([found.label, found.value, found.hint], ['new violations', 1, '1 minor']);
  assert.deepEqual([duration.label, duration.value, duration.hint], ['duration', '5m 28s', 'of 10m']);
});

test('a run that stopped short says how many dimensions finished', () => {
  const [dims] = buildJobStatCells('done', { ...base, dimsDone: 5 });
  assert.equal(dims.hint, null);
  assert.equal(dims.trailing, '/ 7');
});

test('an unlimited finished run says total, and zero violations is not alarming', () => {
  const [, , found, duration] = buildJobStatCells('done', { ...base, budgetS: 0, liveCount: 0, sevCounts: {} });
  assert.equal(duration.hint, 'total');
  assert.notEqual(found.tone, 'critical');
});

test('time past the budget is flagged, running or finished', () => {
  const [, , , duration] = buildJobStatCells('done', { ...base, elapsedS: 700 });
  assert.equal(duration.tone, 'warning');
  const running = buildJobStatCells('running', { ...base, elapsedS: 700 }).at(-1);
  assert.equal(running.tone, 'warning');
  const inBudget = buildJobStatCells('done', base).at(-1);
  assert.equal(inBudget.tone, 'default');
  const unlimited = buildJobStatCells('done', { ...base, budgetS: 0, elapsedS: 99999 }).at(-1);
  assert.equal(unlimited.tone, 'default');
});

test('a run stopped at its time limit, a few seconds past it, is not flagged', () => {
  const [, , , duration] = buildJobStatCells('done', { ...base, elapsedS: 620 });
  assert.equal(duration.tone, 'default');
});
