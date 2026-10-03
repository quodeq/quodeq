import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { STAGE_STATUS } from '../../../vocab/stageStatus.js';
import { useStageExplain, STAGE_DEBOUNCE_MS } from './useStageExplain.js';

const stages = { types: { critical: 0, major: 1, minor: 3 }, complianceTypes: 4, weightedViolations: 2.25, base: 7.87, lift: 0.36, raw: 8.64, ceiling: 9.16, floor: 5, final: 8.6, grade: 'Good' };
const params = { baseK: 0.12 };
const stored = { runId: 'r1', dimension: 'maintainability', params, principles: [{ principleId: 'P1', insufficient: false, stages }] };
const live = { ...stored, params: { baseK: 0.5 }, principles: [{ principleId: 'P1', insufficient: false, stages: { ...stages, final: 7.1, grade: 'Good' } }] };

function mount(api, initial) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }) => createElement(QueryClientProvider, { client },
    createElement(ApiProvider, { value: api }, children));
  return renderHook((props) => useStageExplain(props), { wrapper, initialProps: initial });
}

const base = { project: 'p', runId: 'r1', dimension: 'maintainability', draft: params, enabled: true };

describe('useStageExplain', () => {
  beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
  afterEach(() => { vi.useRealTimers(); });

  it('loads the stored stages and becomes ready', async () => {
    const api = { getGradeExplain: vi.fn(async () => stored), previewGradeExplain: vi.fn(async () => live) };
    const { result } = mount(api, base);
    await waitFor(() => expect(result.current.status).toBe(STAGE_STATUS.READY));
    expect(result.current.stored).toEqual(stored);
    expect(result.current.principles[0].principleId).toBe('P1');
  });

  it('recomputes once after the debounce when the draft changes', async () => {
    const api = { getGradeExplain: vi.fn(async () => stored), previewGradeExplain: vi.fn(async () => live) };
    const { result, rerender } = mount(api, base);
    await waitFor(() => expect(result.current.status).toBe(STAGE_STATUS.READY));
    rerender({ ...base, draft: { baseK: 0.4 } });
    rerender({ ...base, draft: { baseK: 0.5 } });
    await act(async () => { await vi.advanceTimersByTimeAsync(STAGE_DEBOUNCE_MS + 10); });
    await waitFor(() => expect(result.current.live).toEqual(live));
    expect(api.previewGradeExplain).toHaveBeenCalledTimes(1);
    expect(api.previewGradeExplain).toHaveBeenCalledWith('p', 'r1', 'maintainability', { baseK: 0.5 });
  });

  it('is unavailable and silent when disabled', async () => {
    const api = { getGradeExplain: vi.fn(async () => stored), previewGradeExplain: vi.fn(async () => live) };
    const { result, rerender } = mount(api, { ...base, enabled: false });
    expect(result.current.status).toBe(STAGE_STATUS.UNAVAILABLE);
    rerender({ ...base, enabled: false, draft: { baseK: 0.5 } });
    await act(async () => { await vi.advanceTimersByTimeAsync(STAGE_DEBOUNCE_MS + 10); });
    expect(api.getGradeExplain).not.toHaveBeenCalled();
    expect(api.previewGradeExplain).not.toHaveBeenCalled();
    expect(result.current.principles).toEqual([]);
  });

  it('reports an error when the stored stages cannot be read', async () => {
    const api = { getGradeExplain: vi.fn(async () => { throw new Error('boom'); }), previewGradeExplain: vi.fn() };
    const { result } = mount(api, base);
    await waitFor(() => expect(result.current.status).toBe(STAGE_STATUS.ERROR));
    expect(result.current.stored).toBeNull();
  });

  it('lists the principles of the stored payload, not of the draft one', async () => {
    const other = { ...live, principles: [{ principleId: 'Ghost', insufficient: false, stages }] };
    const api = { getGradeExplain: vi.fn(async () => stored), previewGradeExplain: vi.fn(async () => other) };
    const { result, rerender } = mount(api, base);
    await waitFor(() => expect(result.current.status).toBe(STAGE_STATUS.READY));
    rerender({ ...base, draft: { baseK: 0.5 } });
    await act(async () => { await vi.advanceTimersByTimeAsync(STAGE_DEBOUNCE_MS + 10); });
    await waitFor(() => expect(result.current.live).toEqual(other));
    expect(result.current.principles.map((p) => p.principleId)).toEqual(['P1']);
  });

  it('switching dimension drops the previous draft stages and ignores a late response', async () => {
    let resolveFirst;
    const preview = vi.fn()
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValue(live);
    const storedOther = { ...stored, dimension: 'security', principles: [{ principleId: 'S1', insufficient: false, stages }] };
    const api = {
      getGradeExplain: vi.fn(async (p, r, dimension) => (dimension === 'security' ? storedOther : stored)),
      previewGradeExplain: preview,
    };
    const { result, rerender } = mount(api, base);
    await waitFor(() => expect(result.current.status).toBe(STAGE_STATUS.READY));
    rerender({ ...base, draft: { baseK: 0.5 } });
    await act(async () => { await vi.advanceTimersByTimeAsync(STAGE_DEBOUNCE_MS + 10); });
    expect(preview).toHaveBeenCalledTimes(1);
    rerender({ ...base, draft: { baseK: 0.5 }, dimension: 'security' });
    await act(async () => { resolveFirst(live); });
    await waitFor(() => expect(result.current.stored).toEqual(storedOther));
    expect(result.current.live).toBeNull();
    expect(result.current.principles.map((p) => p.principleId)).toEqual(['S1']);
  });

  it('clears the live payload and warns when the preview request fails', async () => {
    const preview = vi.fn().mockResolvedValueOnce(live).mockRejectedValueOnce(new Error('boom'));
    const api = { getGradeExplain: vi.fn(async () => stored), previewGradeExplain: preview };
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { result, rerender } = mount(api, base);
    await waitFor(() => expect(result.current.status).toBe(STAGE_STATUS.READY));
    rerender({ ...base, draft: { baseK: 0.5 } });
    await act(async () => { await vi.advanceTimersByTimeAsync(STAGE_DEBOUNCE_MS + 10); });
    await waitFor(() => expect(result.current.live).toEqual(live));
    rerender({ ...base, draft: { baseK: 9 } });
    await act(async () => { await vi.advanceTimersByTimeAsync(STAGE_DEBOUNCE_MS + 10); });
    await waitFor(() => expect(result.current.live).toBeNull());
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('[grade-formula]'), expect.any(Error));
    warn.mockRestore();
  });

  it('ignores a rejection for a superseded request', async () => {
    let rejectFirst;
    const preview = vi.fn()
      .mockImplementationOnce(() => new Promise((resolve, reject) => { rejectFirst = reject; }))
      .mockResolvedValue(live);
    const api = { getGradeExplain: vi.fn(async () => stored), previewGradeExplain: preview };
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { result, rerender } = mount(api, base);
    await waitFor(() => expect(result.current.status).toBe(STAGE_STATUS.READY));
    rerender({ ...base, draft: { baseK: 0.5 } });
    await act(async () => { await vi.advanceTimersByTimeAsync(STAGE_DEBOUNCE_MS + 10); });
    expect(preview).toHaveBeenCalledTimes(1);
    rerender({ ...base, draft: { baseK: 0.5 }, dimension: 'security' });
    await act(async () => { rejectFirst(new Error('late')); });
    await waitFor(() => expect(result.current.stored).toEqual(stored));
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
