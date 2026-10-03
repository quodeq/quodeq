import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useHistoryDeleteRun } from './useHistoryDeleteRun.js';
import catalog from '../../../strings/en.json' with { type: 'json' };

const showToast = vi.fn();
vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({ showToast }),
}));
vi.mock('../../../utils/confirmDialog.js', () => ({
  confirmDialog: vi.fn().mockResolvedValue(true),
}));

describe('useHistoryDeleteRun failure presentation', () => {
  beforeEach(() => {
    showToast.mockClear();
  });

  it('surfaces a delete failure via showToast, not window.alert', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const deleteEvaluation = vi.fn().mockRejectedValue(new Error('boom'));
    const onRunDeleted = vi.fn();
    const { result } = renderHook(() => useHistoryDeleteRun({ selectedSource: 'local', deleteEvaluation, onRunDeleted }));

    await act(async () => { await result.current.handleDeleteRun('run-1', '2026-09-16'); });

    expect(alertSpy).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith(catalog['history.deleteRunFailed'].replace('{message}', 'boom'));
    expect(onRunDeleted).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('falls back to the unknown-error string when the failure carries no message', async () => {
    const deleteEvaluation = vi.fn().mockRejectedValue({});
    const { result } = renderHook(() => useHistoryDeleteRun({ selectedSource: 'local', deleteEvaluation, onRunDeleted: vi.fn() }));

    await act(async () => { await result.current.handleDeleteRun('run-1'); });

    expect(showToast).toHaveBeenCalledWith(catalog['history.deleteRunFailed'].replace('{message}', catalog['history.unknownError']));
    expect(showToast.mock.calls[0][0]).not.toMatch(/\{message\}/);
  });

  it('does nothing for a shared source', async () => {
    const deleteEvaluation = vi.fn();
    const { result } = renderHook(() => useHistoryDeleteRun({ selectedSource: 'shared', deleteEvaluation, onRunDeleted: vi.fn() }));

    await act(async () => { await result.current.handleDeleteRun('run-1'); });

    expect(deleteEvaluation).not.toHaveBeenCalled();
    expect(showToast).not.toHaveBeenCalled();
  });
});

describe('useHistoryDeleteRun pending state', () => {
  beforeEach(() => { showToast.mockClear(); });

  function deferred() {
    let resolve, reject;
    const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
  }

  it('exposes the run id while the delete is in flight and clears it after', async () => {
    const d = deferred();
    const deleteEvaluation = vi.fn().mockReturnValue(d.promise);
    const onRunDeleted = vi.fn();
    const { result } = renderHook(() => useHistoryDeleteRun({ selectedSource: 'local', deleteEvaluation, onRunDeleted }));
    let call;
    act(() => { call = result.current.handleDeleteRun('run-1', '2026-09-16'); });
    await waitFor(() => expect(result.current.deletingRunIds.has('run-1')).toBe(true));
    await act(async () => { d.resolve({ ok: true }); await call; });
    expect(result.current.deletingRunIds.size).toBe(0);
    expect(onRunDeleted).toHaveBeenCalledWith('run-1');
  });

  it('clears the pending id on failure', async () => {
    const deleteEvaluation = vi.fn().mockRejectedValue(new Error('409 running'));
    const { result } = renderHook(() => useHistoryDeleteRun({ selectedSource: 'local', deleteEvaluation, onRunDeleted: vi.fn() }));
    await act(async () => { await result.current.handleDeleteRun('run-1'); });
    expect(result.current.deletingRunIds.size).toBe(0);
    expect(showToast).toHaveBeenCalledTimes(1);
  });

  it('ignores a second click on the pending row', async () => {
    const d = deferred();
    const deleteEvaluation = vi.fn().mockReturnValue(d.promise);
    const { result } = renderHook(() => useHistoryDeleteRun({ selectedSource: 'local', deleteEvaluation, onRunDeleted: vi.fn() }));
    let first;
    act(() => { first = result.current.handleDeleteRun('run-1'); });
    await waitFor(() => expect(result.current.deletingRunIds.has('run-1')).toBe(true));
    await act(async () => { await result.current.handleDeleteRun('run-1'); });
    expect(deleteEvaluation).toHaveBeenCalledTimes(1);
    await act(async () => { d.resolve({ ok: true }); await first; });
  });

  it('allows a delete of another run while one is pending', async () => {
    const d = deferred();
    const deleteEvaluation = vi.fn().mockReturnValueOnce(d.promise).mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(() => useHistoryDeleteRun({ selectedSource: 'local', deleteEvaluation, onRunDeleted: vi.fn() }));
    let first;
    act(() => { first = result.current.handleDeleteRun('run-1'); });
    await waitFor(() => expect(result.current.deletingRunIds.has('run-1')).toBe(true));
    await act(async () => { await result.current.handleDeleteRun('run-2'); });
    expect(deleteEvaluation).toHaveBeenCalledTimes(2);
    // The first row stays pending while its own request is still out.
    expect(result.current.deletingRunIds.has('run-1')).toBe(true);
    expect(result.current.deletingRunIds.has('run-2')).toBe(false);
    await act(async () => { d.resolve({ ok: true }); await first; });
    expect(result.current.deletingRunIds.size).toBe(0);
  });
});
