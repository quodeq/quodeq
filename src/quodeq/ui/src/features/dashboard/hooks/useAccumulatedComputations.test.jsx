/**
 * computeAccumulatedStats is a plain function, but the module also pulls in
 * ../../../utils/visibleStandards.js -> ../../../api/standards.js, which
 * reads import.meta.env — only Vite (vitest) provides that, so this file
 * must run under vitest (.test.jsx), not node:test (.test.js).
 */
import { describe, it, expect } from 'vitest';
import { computeAccumulatedStats } from './useAccumulatedComputations.js';

describe('computeAccumulatedStats', () => {
  it('sorts accumulated dimensions by name', () => {
    const dims = [
      { dimension: 'security' },
      { dimension: 'clean-arch' },
    ];
    const { sorted } = computeAccumulatedStats(dims, null, null);
    expect(sorted.map((d) => d.dimension)).toEqual(['clean-arch', 'security']);
  });

  it('does not throw when a dimension entry has no dimension name', () => {
    const dims = [
      { dimension: 'security' },
      { dimension: undefined },
      { dimension: 'clean-arch' },
    ];
    expect(() => computeAccumulatedStats(dims, null, null)).not.toThrow();
    const { sorted } = computeAccumulatedStats(dims, null, null);
    expect(sorted).toHaveLength(3);
    // Missing names sort first (empty-string fallback).
    expect(sorted[0].dimension).toBeUndefined();
  });
});
