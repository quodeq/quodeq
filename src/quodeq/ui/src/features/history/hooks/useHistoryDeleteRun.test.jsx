import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
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

    await act(async () => { await result.current('run-1', '2026-09-16'); });

    expect(alertSpy).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith(catalog['history.deleteRunFailed'].replace('{message}', 'boom'));
    expect(onRunDeleted).not.toHaveBeenCalled();
    alertSpy.mockRestore();
  });

  it('falls back to the unknown-error string when the failure carries no message', async () => {
    const deleteEvaluation = vi.fn().mockRejectedValue({});
    const { result } = renderHook(() => useHistoryDeleteRun({ selectedSource: 'local', deleteEvaluation, onRunDeleted: vi.fn() }));

    await act(async () => { await result.current('run-1'); });

    expect(showToast).toHaveBeenCalledWith(catalog['history.deleteRunFailed'].replace('{message}', catalog['history.unknownError']));
    expect(showToast.mock.calls[0][0]).not.toMatch(/\{message\}/);
  });

  it('does nothing for a shared source', async () => {
    const deleteEvaluation = vi.fn();
    const { result } = renderHook(() => useHistoryDeleteRun({ selectedSource: 'shared', deleteEvaluation, onRunDeleted: vi.fn() }));

    await act(async () => { await result.current('run-1'); });

    expect(deleteEvaluation).not.toHaveBeenCalled();
    expect(showToast).not.toHaveBeenCalled();
  });
});
