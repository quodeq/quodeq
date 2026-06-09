import test from 'node:test';
import assert from 'node:assert/strict';
import { recordRateSample, getRateSamples, _resetRateSamples } from './rateSampleStore.js';
import { RATE_WINDOW_MS } from './buildJobStatCells.js';

test('rateSampleStore: records and returns samples for a job', () => {
  _resetRateSamples();
  recordRateSample('j1', 1000, 10);
  recordRateSample('j1', 2000, 12);
  assert.deepEqual(getRateSamples('j1'), [{ t: 1000, taken: 10 }, { t: 2000, taken: 12 }]);
});

test('rateSampleStore: survives reads — a remount keeps appending, not resetting', () => {
  _resetRateSamples();
  recordRateSample('j1', 1000, 10);
  getRateSamples('j1');               // "first mount" reads the buffer
  recordRateSample('j1', 2000, 12);   // "second mount" keeps appending to the same buffer
  assert.equal(getRateSamples('j1').length, 2);
});

test('rateSampleStore: trims samples older than RATE_WINDOW_MS', () => {
  _resetRateSamples();
  const t0 = 1_000_000;
  recordRateSample('j1', t0, 10);
  recordRateSample('j1', t0 + RATE_WINDOW_MS + 1, 40);  // pushes the first out of the window
  const buf = getRateSamples('j1');
  assert.equal(buf.length, 1);
  assert.equal(buf[0].taken, 40);
});

test('rateSampleStore: never empties — keeps the newest even if older than the window', () => {
  _resetRateSamples();
  recordRateSample('j1', 0, 5);
  assert.equal(getRateSamples('j1').length, 1);
});

test('rateSampleStore: isolates samples per job', () => {
  _resetRateSamples();
  recordRateSample('j1', 1000, 10);
  recordRateSample('j2', 1000, 99);
  assert.equal(getRateSamples('j1').length, 1);
  assert.equal(getRateSamples('j2')[0].taken, 99);
});

test('rateSampleStore: returns an empty array for an unknown job', () => {
  _resetRateSamples();
  assert.deepEqual(getRateSamples('nope'), []);
});
