import { describe, it, expect, vi } from 'vitest';
import { computeWeights } from './SidePane.jsx';

describe('computeWeights — stale ratios guard', () => {
  it('splits weights normally when ratios matches windowCount - 1', () => {
    const weights = computeWeights(3, [0.5, 0.5]);
    expect(weights).toHaveLength(3);
    expect(weights.every((w) => Number.isFinite(w))).toBe(true);
  });

  it('falls back to equal weights, without warning, when ratios has more entries than windowCount - 1', () => {
    // Stale ratios from a 4-window layout applied to a 2-window render --
    // a routine transient (useInnerDividerDrag's windowCount effect hasn't
    // caught up yet on this render), not an exceptional condition worth
    // logging on every window add/remove.
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      const weights = computeWeights(2, [0.5, 0.5, 0.5]);
      expect(weights).toEqual([1, 1]);
      expect(weights.every((w) => Number.isFinite(w))).toBe(true);
      expect(warnSpy).not.toHaveBeenCalled();
    } finally {
      warnSpy.mockRestore();
    }
  });
});
