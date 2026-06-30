import test from 'node:test';
import assert from 'node:assert/strict';
import { formatPeriodLabel } from './formatters.js';

const E = { dateISO: '2026-03-25T14:00:00', dateLabel: '25 Mar 2026' };

test('day granularity shows the specific date label', () => {
  assert.equal(formatPeriodLabel(E, 'day'), '25 Mar 2026');
  assert.equal(formatPeriodLabel(E), '25 Mar 2026'); // default day
});

test('month granularity shows month name + year', () => {
  assert.equal(formatPeriodLabel(E, 'month'), 'March 2026');
});

test('week granularity shows ISO week number + year', () => {
  assert.equal(formatPeriodLabel(E, 'week'), 'Week 13, 2026');
});

test('week granularity respects the ISO year-boundary', () => {
  assert.equal(formatPeriodLabel({ dateISO: '2025-12-29T00:00:00' }, 'week'), 'Week 1, 2026');
});

test('falls back to dateLabel when dateISO is missing', () => {
  assert.equal(formatPeriodLabel({ dateLabel: 'Latest' }, 'month'), 'Latest');
  assert.equal(formatPeriodLabel({ dateLabel: 'Latest' }, 'week'), 'Latest');
});
