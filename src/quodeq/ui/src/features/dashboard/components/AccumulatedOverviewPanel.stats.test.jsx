import { describe, it, expect } from 'vitest';
import { computeAccumulatedStats } from './AccumulatedOverviewPanel.jsx';

const dims = [
  { dimension: 'security', fromRunId: 'r1', fromDateIso: '2026-01-02', fromDateLabel: 'Jan 2' },
];

describe('computeAccumulatedStats scoreDelta', () => {
  it('is null with fewer than two trend entries (no apples-to-oranges fallback)', () => {
    const { scoreDelta } = computeAccumulatedStats(
      dims, [{ runId: 'r1', numericAverage: '7.0' }], 'r1',
    );
    expect(scoreDelta).toBeNull();
  });

  it('subtracts this run vs the previous run when two or more entries exist', () => {
    const trend = [
      { runId: 'r2', numericAverage: '8.0' },
      { runId: 'r1', numericAverage: '7.0' },
    ];
    const { scoreDelta } = computeAccumulatedStats(dims, trend, 'r2');
    expect(scoreDelta).toBe('1.0');
  });

  it('uses the selected run index for the delta', () => {
    const trend = [
      { runId: 'r3', numericAverage: '9.0' },
      { runId: 'r2', numericAverage: '8.0' },
      { runId: 'r1', numericAverage: '6.5' },
    ];
    // Selecting r2 compares r2 (8.0) against the older r1 (6.5) = 1.5.
    const { scoreDelta } = computeAccumulatedStats(dims, trend, 'r2');
    expect(scoreDelta).toBe('1.5');
  });
});
