import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import useGradeFormula from './useGradeFormula.js';
import { RESCORE_POLL_MS } from './hooks/useRescoreProgress.js';
import { projectKeys } from '../../api/queryKeys.js';

vi.mock('../../api/index.js', () => ({
  getGradeFormula: vi.fn(),
  saveGradeFormula: vi.fn(),
  resetGradeFormula: vi.fn(),
  previewGradeFormula: vi.fn(),
}));

vi.mock('../../utils/gradeThresholds.js', () => ({
  defaultGradeThresholdsStore: { set: vi.fn() },
}));

import { getGradeFormula, saveGradeFormula, previewGradeFormula } from '../../api/index.js';

const CURRENT = {
  severityWeight: 1, baseK: 5, liftCompress: 0.5, ceilScale: 1,
  floorMinor: 8, floorMajor: 5,
  gradeThresholds: [[9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor']],
  dimensionWeightsEnabled: false, dimensionWeights: {},
};
const SAVED = { ...CURRENT, baseK: 9 };

function rescore(over = {}) {
  return { state: 'running', generation: 1, appliedGeneration: 0, done: 0, total: 3, failed: 0, ...over };
}
function payload(current, r) {
  return { current, defaults: CURRENT, isCustom: current !== CURRENT, rescore: r };
}
const IDLE_START = rescore({ state: 'idle', generation: 0, total: 0 });
const LANDED = rescore({ state: 'idle', appliedGeneration: 1, done: 3 });

let queryClient;
let invalidateSpy;

function wrapper({ children }) {
  return createElement(QueryClientProvider, { client: queryClient }, children);
}

async function tick(times = 1) {
  await act(async () => { await vi.advanceTimersByTimeAsync(RESCORE_POLL_MS * times); });
}

async function mountAndApply() {
  const hook = renderHook(() => useGradeFormula('proj'), { wrapper });
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  await act(async () => { await hook.result.current.apply(); });
  return hook;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
  getGradeFormula.mockReset();
  getGradeFormula.mockResolvedValueOnce(payload(CURRENT, IDLE_START));
  saveGradeFormula.mockResolvedValue(payload(SAVED, rescore()));
  previewGradeFormula.mockResolvedValue({
    project: 'proj', runId: 'r1',
    before: { overall: { score: 7, grade: 'Good' }, dimensions: [] },
    after: { overall: { score: 7, grade: 'Good' }, dimensions: [] },
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useGradeFormula background rescore', () => {
  it('adopts the 202 at once and reports progress without invalidating yet', async () => {
    getGradeFormula.mockResolvedValue(payload(SAVED, rescore({ done: 1 })));
    const { result } = await mountAndApply();
    expect(result.current.isCustom).toBe(true);
    expect(result.current.draft).toEqual(SAVED);
    expect(result.current.rescoreProgress).not.toBeNull();
    await tick();
    expect(result.current.rescoreProgress).toEqual({ done: 1, total: 3 });
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('polls until the pass lands, then invalidates the score queries once and stops', async () => {
    getGradeFormula
      .mockResolvedValueOnce(payload(SAVED, rescore({ done: 1 })))
      .mockResolvedValueOnce(payload(SAVED, rescore({ done: 2 })))
      .mockResolvedValue(payload(SAVED, LANDED));
    const { result } = await mountAndApply();
    await tick(4);
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: projectKeys.all() });
    expect(result.current.rescoreProgress).toBeNull();
    expect(result.current.partialNotice).toBeNull();
    const polls = getGradeFormula.mock.calls.length;
    await tick(3);
    expect(getGradeFormula.mock.calls.length).toBe(polls);
  });

  it('stops polling on unmount', async () => {
    getGradeFormula.mockResolvedValue(payload(SAVED, rescore({ done: 1 })));
    const { unmount } = await mountAndApply();
    await tick();
    unmount();
    const polls = getGradeFormula.mock.calls.length;
    await tick(5);
    expect(getGradeFormula.mock.calls.length).toBe(polls);
    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it('shows the partial-failure notice when the landed pass has failed runs', async () => {
    getGradeFormula.mockResolvedValue(payload(SAVED, { ...LANDED, failed: 2 }));
    const { result } = await mountAndApply();
    await tick(2);
    expect(result.current.partialNotice).toBe(
      'Applied, but 2 runs could not be rescored and still show the old formula. Try applying again.',
    );
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
  });

  it('stops polling and surfaces the failure when the pass errors', async () => {
    getGradeFormula.mockResolvedValue(payload(SAVED, rescore({ state: 'error' })));
    const { result } = await mountAndApply();
    await tick(2);
    expect(result.current.error).toBe('Rescore failed. Some runs may still show the old formula. Try applying again.');
    expect(result.current.rescoreProgress).toBeNull();
    const polls = getGradeFormula.mock.calls.length;
    await tick(3);
    expect(getGradeFormula.mock.calls.length).toBe(polls);
  });

  it('stops polling when the server restarted and lost the job', async () => {
    getGradeFormula.mockResolvedValue(payload(SAVED, IDLE_START));
    const { result } = await mountAndApply();
    await tick(2);
    expect(result.current.rescoreProgress).toBeNull();
    const polls = getGradeFormula.mock.calls.length;
    await tick(3);
    expect(getGradeFormula.mock.calls.length).toBe(polls);
  });

  it('keeps polling after one failed poll and still lands', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    getGradeFormula
      .mockRejectedValueOnce(new Error('blip'))
      .mockResolvedValue(payload(SAVED, LANDED));
    await mountAndApply();
    await tick(3);
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    warn.mockRestore();
  });

  it('resumes polling on mount when a pass is already running', async () => {
    getGradeFormula.mockReset();
    getGradeFormula
      .mockResolvedValueOnce(payload(SAVED, rescore({ done: 1 })))
      .mockResolvedValue(payload(SAVED, LANDED));
    renderHook(() => useGradeFormula('proj'), { wrapper });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    // Only a tracked pass can settle and invalidate, so this proves the
    // mount GET's running pass was picked up without any apply.
    await tick(2);
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(saveGradeFormula).not.toHaveBeenCalled();
  });
});
