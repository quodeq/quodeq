import { describe, it, expect } from 'vitest';
import { computeDeltas } from './HistoryContent.jsx';

// Rows are newest-first and may carry scoreless stubs (in-progress runs,
// cancelled partials). A scored row's delta is against the next SCORED row.
describe('computeDeltas', () => {
  it('compares each scored row against the next scored row, skipping scoreless stubs', () => {
    const rows = [
      { numericAverage: '8.4' },
      { numericAverage: null },      // in-progress stub
      { numericAverage: '7.9' },
      { numericAverage: undefined }, // cancelled partial
      { numericAverage: '' },
      { numericAverage: '8.1' },
    ];
    expect(computeDeltas(rows)).toEqual([0.5, null, -0.2, null, null, null]);
  });

  it('returns null everywhere when fewer than two rows are scored', () => {
    expect(computeDeltas([])).toEqual([]);
    expect(computeDeltas([{ numericAverage: '7' }])).toEqual([null]);
    expect(computeDeltas([{ numericAverage: null }, { numericAverage: '7' }])).toEqual([null, null]);
  });

  it('reads every row exactly once', () => {
    // A run of stubs between scored rows used to be re-parsed by every
    // earlier scored row; a single pass touches each row once.
    let reads = 0;
    const rows = Array.from({ length: 12 }, (_, i) => ({
      get numericAverage() { reads++; return i % 3 === 0 ? String(9 - i / 3) : null; },
    }));
    const deltas = computeDeltas(rows);
    expect(reads).toBe(rows.length);
    expect(deltas[0]).toBe(1);
    expect(deltas[9]).toBeNull();
  });
});
