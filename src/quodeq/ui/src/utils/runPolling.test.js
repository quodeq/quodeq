import test from 'node:test';
import assert from 'node:assert/strict';
import { pollIntervalForRuns, IN_PROGRESS_POLL_MS } from './runPolling.js';

test('returns false when there are no runs', () => {
  assert.equal(pollIntervalForRuns([]), false);
  assert.equal(pollIntervalForRuns(null), false);
  assert.equal(pollIntervalForRuns(undefined), false);
});

test('returns false when every run is terminal', () => {
  const runs = [
    { runId: 'r1', status: 'complete' },
    { runId: 'r2', status: 'cancelled' },
    { runId: 'r3', status: 'failed' },
  ];
  assert.equal(pollIntervalForRuns(runs), false);
});

test('returns the poll interval when at least one run is in_progress', () => {
  const runs = [
    { runId: 'r1', status: 'in_progress' },
    { runId: 'r2', status: 'complete' },
  ];
  assert.equal(pollIntervalForRuns(runs), IN_PROGRESS_POLL_MS);
});

test('IN_PROGRESS_POLL_MS is in the 10-30 second range', () => {
  // Background-poll cadence: tight enough to flip the row within
  // seconds of the umbrella run terminating, loose enough that a
  // local server with one running scan barely notices. Polling is
  // History-page-only, not global. If this constant moves outside
  // the band, revisit the UX/perf tradeoff.
  assert.ok(IN_PROGRESS_POLL_MS >= 10000 && IN_PROGRESS_POLL_MS <= 30000);
});

test('treats missing status as not in_progress (defensive)', () => {
  const runs = [
    { runId: 'r1' },
    { runId: 'r2', status: undefined },
  ];
  assert.equal(pollIntervalForRuns(runs), false);
});
