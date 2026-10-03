import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useVisibleStandardsFiltered } from './useAppShellHooks.js';

// DEFAULT_VISIBLE_STANDARDS (constants.js) includes 'security' but not
// 'made-up-dim', so with nothing in localStorage the default set governs
// what's visible here -- same as the app's first-run state.

function trendEntry(runId, dims) {
  return {
    runId,
    dimensionDetails: dims.map(([dimension, score]) => ({ dimension, score })),
    dimensions: dims.map(([dimension]) => dimension),
  };
}

describe('useVisibleStandardsFiltered', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('filters trend entries to only the visible standards', () => {
    const state = {
      dashboard: {
        trend: [
          trendEntry('r1', [['security', 8], ['made-up-dim', 2]]),
        ],
      },
      accumulated: null,
    };
    const { result } = renderHook(() => useVisibleStandardsFiltered(state));

    expect(result.current.filteredTrend).toHaveLength(1);
    const dims = result.current.filteredTrend[0].dimensionDetails.map((d) => d.dimension);
    expect(dims).toEqual(['security']);
  });

  it('drops trend entries left with no visible dimensions', () => {
    const state = {
      dashboard: { trend: [trendEntry('r1', [['made-up-dim', 2]])] },
      accumulated: null,
    };
    const { result } = renderHook(() => useVisibleStandardsFiltered(state));

    expect(result.current.filteredTrend).toEqual([]);
  });

  it('filters accumulated dimensions to only the visible standards', () => {
    const state = {
      dashboard: { trend: [] },
      accumulated: {
        dimensions: [
          { dimension: 'security', totals: { violationCount: 0, complianceCount: 0 } },
          { dimension: 'made-up-dim', totals: { violationCount: 0, complianceCount: 0 } },
        ],
        summary: { numericAverage: 7.0 },
      },
    };
    const { result } = renderHook(() => useVisibleStandardsFiltered(state));

    expect(result.current.filteredAccumulated.dimensions.map((d) => d.dimension)).toEqual(['security']);
  });

  it('null accumulated stays null', () => {
    const state = { dashboard: { trend: [] }, accumulated: null };
    const { result } = renderHook(() => useVisibleStandardsFiltered(state));

    expect(result.current.filteredAccumulated).toBeNull();
  });
});
