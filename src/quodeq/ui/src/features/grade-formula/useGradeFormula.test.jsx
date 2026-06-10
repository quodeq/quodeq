import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import useGradeFormula from './useGradeFormula.js';
import { projectKeys } from '../../api/queryKeys.js';

vi.mock('../../api/index.js', () => ({
  getGradeFormula: vi.fn(),
  saveGradeFormula: vi.fn(),
  resetGradeFormula: vi.fn(),
  previewGradeFormula: vi.fn(),
}));

vi.mock('../../utils/gradeThresholds.js', () => ({
  setGradeThresholds: vi.fn(),
}));

import {
  getGradeFormula, saveGradeFormula, resetGradeFormula, previewGradeFormula,
} from '../../api/index.js';
import { setGradeThresholds } from '../../utils/gradeThresholds.js';

// The hook lives inside the React Query provider tree in the real app, so the
// tests wrap renderHook in a QueryClientProvider. invalidateSpy lets the
// apply/reset tests assert the score caches are dropped.
let queryClient;
let invalidateSpy;

function wrapper({ children }) {
  return createElement(QueryClientProvider, { client: queryClient }, children);
}

function renderGradeFormula(projectId) {
  return renderHook(() => useGradeFormula(projectId), { wrapper });
}

const CURRENT = {
  severityWeight: 1, baseK: 5, liftCompress: 0.5, ceilScale: 1,
  floorMinor: 8, floorMajor: 5,
  gradeThresholds: [[9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor']],
  dimensionWeightsEnabled: false, dimensionWeights: {},
};
const DEFAULTS = { ...CURRENT };

beforeEach(() => {
  vi.clearAllMocks();
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
  getGradeFormula.mockResolvedValue({ current: CURRENT, defaults: DEFAULTS, isCustom: false });
  previewGradeFormula.mockResolvedValue({
    project: 'proj', runId: 'r1',
    before: { overall: { score: 7, grade: 'Good' }, dimensions: [] },
    after: { overall: { score: 7, grade: 'Good' }, dimensions: [] },
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useGradeFormula', () => {
  it('loads params on mount', async () => {
    const { result } = renderGradeFormula('proj');
    await waitFor(() => expect(result.current.draft).toEqual(CURRENT));
    expect(result.current.defaults).toEqual(DEFAULTS);
    expect(result.current.isCustom).toBe(false);
    expect(result.current.isDirty).toBeFalsy();
  });

  it('update() marks the draft dirty and fires a debounced preview', async () => {
    vi.useFakeTimers();
    const { result } = renderGradeFormula('proj');
    // Flush the mount GET and the initial preview.
    await act(async () => { await vi.runAllTimersAsync(); });
    previewGradeFormula.mockClear();

    act(() => { result.current.update({ baseK: 9 }); });

    expect(result.current.draft.baseK).toBe(9);
    expect(result.current.isDirty).toBe(true);
    // Debounced: no call until the timer elapses.
    expect(previewGradeFormula).not.toHaveBeenCalled();

    await act(async () => { await vi.advanceTimersByTimeAsync(300); });
    expect(previewGradeFormula).toHaveBeenCalledWith('proj', expect.objectContaining({ baseK: 9 }));
  });

  it('does not request a preview when projectId is null', async () => {
    vi.useFakeTimers();
    const { result } = renderGradeFormula(null);
    await act(async () => { await vi.runAllTimersAsync(); });

    act(() => { result.current.update({ baseK: 9 }); });
    await act(async () => { await vi.advanceTimersByTimeAsync(300); });

    expect(previewGradeFormula).not.toHaveBeenCalled();
  });

  it('apply() saves the draft and pushes thresholds into the gradeThresholds store', async () => {
    const saved = {
      ...CURRENT, baseK: 9,
      gradeThresholds: [[8, 'Exemplary'], [6, 'Good'], [4, 'Adequate'], [2, 'Poor']],
    };
    saveGradeFormula.mockResolvedValue({
      current: saved, defaults: DEFAULTS, isCustom: true, applied: 3,
    });
    const { result } = renderGradeFormula('proj');
    await waitFor(() => expect(result.current.draft).toEqual(CURRENT));

    let applied;
    await act(async () => { applied = await result.current.apply(); });

    expect(saveGradeFormula).toHaveBeenCalledWith(CURRENT);
    expect(setGradeThresholds).toHaveBeenCalledWith(saved.gradeThresholds);
    expect(applied).toBe(3);
    expect(result.current.isCustom).toBe(true);
    expect(result.current.draft).toEqual(saved);
    expect(result.current.isDirty).toBeFalsy();
    // Apply rewrote every run's grades server-side: the cached score/dashboard
    // queries must be invalidated so they refetch.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: projectKeys.all() });
  });

  it('resetToDefaults() restores defaults and reseeds the thresholds store', async () => {
    resetGradeFormula.mockResolvedValue({
      current: DEFAULTS, defaults: DEFAULTS, isCustom: false, applied: 2,
    });
    const { result } = renderGradeFormula('proj');
    await waitFor(() => expect(result.current.draft).toEqual(CURRENT));

    await act(async () => { await result.current.resetToDefaults(); });

    expect(resetGradeFormula).toHaveBeenCalledTimes(1);
    expect(setGradeThresholds).toHaveBeenCalledWith(DEFAULTS.gradeThresholds);
    expect(result.current.isCustom).toBe(false);
    // Reset also re-baked grades server-side: invalidate the score caches.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: projectKeys.all() });
  });

  it('surfaces a load error when the initial GET rejects', async () => {
    getGradeFormula.mockRejectedValueOnce(new Error('boom'));
    const { result } = renderGradeFormula('proj');
    await waitFor(() => expect(result.current.error).toBe('Could not load grade formula'));
  });
});
