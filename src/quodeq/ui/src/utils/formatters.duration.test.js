import test from 'node:test';
import assert from 'node:assert/strict';
import { formatDuration, formatDurationCoarse } from './formatters.js';

test('formatDuration: seconds only under a minute', () => {
  assert.equal(formatDuration(0), '0s');
  assert.equal(formatDuration(42), '42s');
  assert.equal(formatDuration(59.9), '59s'); // floors, never rounds up
});

test('formatDuration: minutes and seconds under an hour', () => {
  assert.equal(formatDuration(60), '1m 0s');
  assert.equal(formatDuration(134), '2m 14s');
  assert.equal(formatDuration(3599), '59m 59s');
});

test('formatDuration: hours from 3600s up (the 255:12 case reads 4h 15m 12s)', () => {
  assert.equal(formatDuration(3600), '1h 0m 0s');
  assert.equal(formatDuration(15312), '4h 15m 12s');
  assert.equal(formatDuration(90000), '25h 0m 0s'); // no day rollover
});

test('formatDuration: "—" for unknown, clamps negatives to 0s', () => {
  assert.equal(formatDuration(null), '—');
  assert.equal(formatDuration(undefined), '—');
  assert.equal(formatDuration(NaN), '—');
  assert.equal(formatDuration(Infinity), '—');
  assert.equal(formatDuration(-5), '0s');
});

test('formatDurationCoarse: drops zero components for round targets', () => {
  assert.equal(formatDurationCoarse(7200), '2h');
  assert.equal(formatDurationCoarse(5400), '1h 30m');
  assert.equal(formatDurationCoarse(600), '10m');
  assert.equal(formatDurationCoarse(30), '30s');
  assert.equal(formatDurationCoarse(0), '0s');
});

test('formatDurationCoarse: seconds appear only under a minute', () => {
  assert.equal(formatDurationCoarse(90), '1m'); // 1m 30s truncates to the minute
  assert.equal(formatDurationCoarse(3661), '1h 1m');
  assert.equal(formatDurationCoarse(null), '—');
});
