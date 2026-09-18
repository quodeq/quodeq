/**
 * Isolated in its own file (not SidePane.test.jsx) so the module-level
 * "warned once" flag in SidePane.jsx isn't polluted by the full-render
 * SidePane tests, which legitimately hit the same stale-ratios path for one
 * transient render whenever a window is added/removed (see
 * useInnerDividerDrag's windowCount effect).
 */
import { describe, it, expect, vi } from 'vitest';
import { computeWeights } from './SidePane.jsx';

describe('computeWeights — stale ratios guard', () => {
  it('splits weights normally when ratios matches windowCount - 1', () => {
    const weights = computeWeights(3, [0.5, 0.5]);
    expect(weights).toHaveLength(3);
    expect(weights.every((w) => Number.isFinite(w))).toBe(true);
  });

  it('falls back to equal weights and warns once when ratios has more entries than windowCount - 1', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      // Stale ratios from a 4-window layout applied to a 2-window render.
      const weights = computeWeights(2, [0.5, 0.5, 0.5]);
      expect(weights).toEqual([1, 1]);
      expect(weights.every((w) => Number.isFinite(w))).toBe(true);
      expect(warnSpy).toHaveBeenCalledTimes(1);

      // A second mismatched call in the same session does not warn again.
      computeWeights(2, [0.5, 0.5, 0.5]);
      expect(warnSpy).toHaveBeenCalledTimes(1);
    } finally {
      warnSpy.mockRestore();
    }
  });
});
