import test from 'node:test';
import assert from 'node:assert/strict';
import { buildJobStatCells } from './buildJobStatCells.js';
import { sumProgressViolations } from './scanProgressTotals.js';

// A dimension's findings reach the strip only through its report, which is
// written when the dimension completes. Until then liveCount is 0 however
// much the agents have found, so the violations tile must not read that as
// "none yet" — on a single-dimension run it would say so for the whole scan.

const runningInputs = {
  overallPct: 1,
  takenFiles: 30,
  totalFiles: 2923,
  elapsedS: 112,
  liveCount: 0,
  sevCounts: { critical: 0, major: 0, minor: 0 },
  dimCycle: { current: 'security', index: 1, count: 1, next: null },
};

function violationsCell(inputs) {
  return buildJobStatCells('running', inputs).find((c) => c.label === 'violations');
}

test('violations tile reports pending, not "none yet", before any report lands', () => {
  const cell = violationsCell({ ...runningInputs, pendingCount: 17 });
  assert.equal(cell.value, 17);
  assert.match(cell.hint, /listed when the dimension finishes/);
  assert.doesNotMatch(cell.hint, /none yet/);
});

test('a pending count stays neutral in tone: it is raw and unconsolidated', () => {
  const cell = violationsCell({ ...runningInputs, pendingCount: 17 });
  assert.equal(cell.tone, 'default');
});

test('pending hint still discloses suppressed and carried counts', () => {
  const cell = violationsCell({
    ...runningInputs, pendingCount: 17, suppressedCount: 3, carriedCount: 2,
  });
  assert.match(cell.hint, /3 suppressed/);
});

test('"none yet" survives when the run has genuinely found nothing', () => {
  const cell = violationsCell({ ...runningInputs, pendingCount: 0 });
  assert.equal(cell.value, 0);
  assert.match(cell.hint, /none yet/);
});

test('listed findings win over the live count once a report exists', () => {
  // Both numbers are available on a multi-dimension run the moment the first
  // dimension finishes. The tile must keep reading the feed's source, or it
  // reintroduces the strip/feed drift of #878.
  const cell = violationsCell({
    ...runningInputs,
    liveCount: 4,
    sevCounts: { critical: 1, major: 3, minor: 0 },
    pendingCount: 17,
  });
  assert.equal(cell.value, 4);
  assert.match(cell.hint, /1 critical · 3 major/);
});

test('sumProgressViolations totals the live per-dimension counts', () => {
  assert.equal(sumProgressViolations({
    dimensions: [
      { id: 'security', state: 'running', violations: 17 },
      { id: 'reliability', state: 'pending', violations: 0 },
    ],
  }), 17);
});

test('sumProgressViolations tolerates missing progress and missing counts', () => {
  assert.equal(sumProgressViolations(null), 0);
  assert.equal(sumProgressViolations({}), 0);
  assert.equal(sumProgressViolations({ dimensions: [{ id: 'security' }] }), 0);
});
