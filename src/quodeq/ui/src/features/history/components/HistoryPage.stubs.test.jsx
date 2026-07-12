import { describe, it, expect } from 'vitest';
import { assembleHistoryRows, visibleHistoryRows } from './HistoryPage.jsx';

// Cancelled runs are stripped from `trend` server-side (they're not chart
// points), but the Overview still shows their kept-findings scores when no
// complete run exists. History must therefore surface them too, or an
// all-cancelled project shows Overview scores over an empty History table.
describe('assembleHistoryRows', () => {
  it('surfaces a cancelled run (absent from trend) as a partial, dated row', () => {
    const availableRuns = [
      { runId: 'r-cancelled', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z', dateLabel: '2 May 2026' },
    ];
    const rows = assembleHistoryRows(availableRuns, []);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      runId: 'r-cancelled', status: 'cancelled', hasScoredDims: true,
      dateISO: '2026-05-02T10:00:00Z',
    });
  });

  it('interleaves cancelled runs with trend rows by date, newest first', () => {
    const trend = [
      { runId: 't-new', status: 'complete', dateISO: '2026-05-03T10:00:00Z', numericAverage: 9 },
      { runId: 't-old', status: 'complete', dateISO: '2026-05-01T10:00:00Z', numericAverage: 7 },
    ];
    const availableRuns = [
      { runId: 't-new', status: 'complete', dateISO: '2026-05-03T10:00:00Z' },
      { runId: 'r-cancelled', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z', dateLabel: '2 May' },
      { runId: 't-old', status: 'complete', dateISO: '2026-05-01T10:00:00Z' },
    ];
    const rows = assembleHistoryRows(availableRuns, trend);
    expect(rows.map((r) => r.runId)).toEqual(['t-new', 'r-cancelled', 't-old']);
  });

  it('keeps in-progress runs on top and does not duplicate trend runs', () => {
    const trend = [{ runId: 't1', status: 'complete', dateISO: '2026-05-01T10:00:00Z', numericAverage: 8 }];
    const availableRuns = [
      { runId: 'live', status: 'in_progress', dateLabel: 'now' },
      { runId: 't1', status: 'complete', dateISO: '2026-05-01T10:00:00Z' },
    ];
    const rows = assembleHistoryRows(availableRuns, trend);
    expect(rows.map((r) => r.runId)).toEqual(['live', 't1']);
    expect(rows[0].status).toBe('in_progress');
  });
});

describe('visibleHistoryRows', () => {
  it('surfaces cancelled runs even when trend is empty (all-cancelled project)', () => {
    // The empty-trend "no evaluations yet" guard must not hide cancelled
    // runs whose scores the Overview shows.
    const availableRuns = [
      { runId: 'c1', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z', dateLabel: '2 May' },
      { runId: 'c2', status: 'cancelled', dateISO: '2026-05-01T10:00:00Z', dateLabel: '1 May' },
    ];
    const rows = visibleHistoryRows(availableRuns, []);
    expect(rows.map((r) => r.runId)).toEqual(['c1', 'c2']);
  });

  it('excludes failed runs (all-failed project stays empty)', () => {
    const availableRuns = [
      { runId: 'f1', status: 'failed', dateISO: '2026-05-01T10:00:00Z' },
    ];
    expect(visibleHistoryRows(availableRuns, [])).toEqual([]);
  });
});
