import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildJobStatCells } from './buildJobStatCells.js';

// The running tiles say what this run is doing, briefly: its new findings,
// the files it targets, and the time against the run's own budget.
const base = {
  overallPct: 83, takenFiles: 221, totalFiles: 265, elapsedS: 214, liveCount: 14,
  sevCounts: { critical: 0, major: 7, minor: 7 }, suppressedCount: 43, carriedCount: 64,
  dimCycle: { current: 'usability', index: 4, count: 7, next: 'performance' }, scanMode: 'incremental',
};

test('running tiles: new violations, short hints, the run budget', () => {
  const [, files, found, elapsed] = buildJobStatCells('running', { ...base, budgetS: 600, etaHint: '~2m left' });
  assert.equal(files.hint, 'changed files');
  assert.equal(found.label, 'new violations');
  assert.equal(found.hint, '7 major · 7 minor');
  assert.equal(elapsed.hint, 'of 10m');
});

test('unlimited run keeps the ETA hint', () => {
  const [, , , elapsed] = buildJobStatCells('running', { ...base, budgetS: 0, etaHint: '~2m left' });
  assert.equal(elapsed.hint, '~2m left');
});

test('a clean scan says files, not changed files', () => {
  const [, files] = buildJobStatCells('running', { ...base, scanMode: 'clean', budgetS: 600 });
  assert.equal(files.hint, 'files');
});

test('zero new violations is not shown as critical', () => {
  const [, , found] = buildJobStatCells('running', { ...base, liveCount: 0, sevCounts: {}, budgetS: 600 });
  assert.notEqual(found.tone, 'critical');
});
