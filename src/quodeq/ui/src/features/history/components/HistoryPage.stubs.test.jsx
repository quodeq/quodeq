import { describe, it, expect } from 'vitest';
import { assembleHistoryRows, visibleHistoryRows } from './HistoryPage.jsx';

// Cancelled runs are stripped from `trend` server-side (they're not chart
// points). The ones that scored a dimension arrive as `partialRuns`, with the
// run's own grade and score, and History lists them between the trend rows.
// A cancelled run with nothing scored has no row.
describe('assembleHistoryRows', () => {
  const partial = { runId: 'r-cancelled', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z', dateLabel: '2 May 2026', runNumericAverage: 6.5, runOverallGrade: 'Adequate', dimensionsCount: 1, numericAverage: null };

  it('lists a partial run with its own values', () => {
    const availableRuns = [{ runId: 'r-cancelled', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z' }];
    const rows = assembleHistoryRows(availableRuns, [], [partial]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ runId: 'r-cancelled', status: 'cancelled', runNumericAverage: 6.5, numericAverage: null });
  });

  it('gives a cancelled run with nothing scored no row', () => {
    const availableRuns = [{ runId: 'r-nothing', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z' }];
    expect(assembleHistoryRows(availableRuns, [], [])).toEqual([]);
  });

  it('interleaves partial runs with trend rows by date, newest first', () => {
    const trend = [
      { runId: 't-new', status: 'done', dateISO: '2026-05-03T10:00:00Z', numericAverage: 9 },
      { runId: 't-old', status: 'done', dateISO: '2026-05-01T10:00:00Z', numericAverage: 7 },
    ];
    const availableRuns = [
      { runId: 't-new', status: 'done', dateISO: '2026-05-03T10:00:00Z' },
      { runId: 'r-cancelled', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z' },
      { runId: 't-old', status: 'done', dateISO: '2026-05-01T10:00:00Z' },
    ];
    const rows = assembleHistoryRows(availableRuns, trend, [partial]);
    expect(rows.map((r) => r.runId)).toEqual(['t-new', 'r-cancelled', 't-old']);
  });

  it('does not list a partial run the trend already carries', () => {
    const trend = [{ runId: 'r-cancelled', status: 'done', dateISO: '2026-05-02T10:00:00Z', numericAverage: 8 }];
    const rows = assembleHistoryRows([], trend, [partial]);
    expect(rows).toHaveLength(1);
    expect(rows[0].numericAverage).toBe(8);
  });

  it('keeps in-progress runs on top and does not duplicate trend runs', () => {
    const trend = [{ runId: 't1', status: 'done', dateISO: '2026-05-01T10:00:00Z', numericAverage: 8 }];
    const availableRuns = [
      { runId: 'live', status: 'running', dateLabel: 'now' },
      { runId: 't1', status: 'done', dateISO: '2026-05-01T10:00:00Z' },
    ];
    const rows = assembleHistoryRows(availableRuns, trend);
    expect(rows.map((r) => r.runId)).toEqual(['live', 't1']);
    expect(rows[0].status).toBe('running');
  });
});

describe('visibleHistoryRows', () => {
  it('lists an all-cancelled project from its partial runs', () => {
    // The empty-trend "no evaluations yet" guard must not hide runs whose
    // scores the Overview shows.
    const availableRuns = [
      { runId: 'c1', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z' },
      { runId: 'c2', status: 'cancelled', dateISO: '2026-05-01T10:00:00Z' },
    ];
    const partialRuns = [
      { runId: 'c1', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z', runNumericAverage: 6 },
      { runId: 'c2', status: 'cancelled', dateISO: '2026-05-01T10:00:00Z', runNumericAverage: 5 },
    ];
    const rows = visibleHistoryRows(availableRuns, [], partialRuns);
    expect(rows.map((r) => r.runId)).toEqual(['c1', 'c2']);
  });

  it('excludes failed runs (all-failed project stays empty)', () => {
    const availableRuns = [
      { runId: 'f1', status: 'failed', dateISO: '2026-05-01T10:00:00Z' },
    ];
    expect(visibleHistoryRows(availableRuns, [])).toEqual([]);
  });
});
