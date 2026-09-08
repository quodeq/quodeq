import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePullToLocal } from './usePullToLocal.js';
import catalog from '../../../strings/en.json' with { type: 'json' };

const showToast = vi.fn();
vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({ showToast }),
}));

describe('usePullToLocal failure presentation', () => {
  beforeEach(() => {
    showToast.mockClear();
  });


  it('handlePull surfaces a non-409 failure via showToast, not window.alert', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const shared = { pull: vi.fn().mockRejectedValue({ status: 500, message: 'boom' }) };
    const { result } = renderHook(() => usePullToLocal({ shared, onProjectsReload: vi.fn() }));

    await act(async () => { await result.current.handlePull('proj-1'); });

    expect(alertSpy).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledTimes(1);
    alertSpy.mockRestore();
  });

  it('handleConfirmCopy surfaces a failure via showToast, not window.alert', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const shared = { pull: vi.fn().mockRejectedValue({ status: 500, message: 'boom' }) };
    const { result } = renderHook(() => usePullToLocal({ shared, onProjectsReload: vi.fn() }));

    await act(async () => { await result.current.handleConfirmCopy('proj-1'); });

    expect(alertSpy).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledTimes(1);
    alertSpy.mockRestore();
  });

  it('handlePull shows the mapped translation for a mapped code, not the raw backend message', async () => {
    const shared = { pull: vi.fn().mockRejectedValue({ status: 500, code: 'PROJECT_EXISTS', message: 'raw backend sentence' }) };
    const { result } = renderHook(() => usePullToLocal({ shared, onProjectsReload: vi.fn() }));

    await act(async () => { await result.current.handlePull('proj-1'); });

    expect(showToast).toHaveBeenCalledWith(catalog['apiError.projectExists']);
  });

  it('handlePull falls back to the bare pullFailed string, with no {message} left unfilled, when the error carries no message', async () => {
    const shared = { pull: vi.fn().mockRejectedValue({ status: 500 }) };
    const { result } = renderHook(() => usePullToLocal({ shared, onProjectsReload: vi.fn() }));

    await act(async () => { await result.current.handlePull('proj-1'); });

    expect(showToast).toHaveBeenCalledWith(catalog['projects.pullFailed']);
    expect(showToast.mock.calls[0][0]).not.toMatch(/\{message\}/);
  });

  it('handleConfirmCopy falls back to the bare pullFailed string when the error carries no message', async () => {
    const shared = { pull: vi.fn().mockRejectedValue({ status: 500 }) };
    const { result } = renderHook(() => usePullToLocal({ shared, onProjectsReload: vi.fn() }));

    await act(async () => { await result.current.handleConfirmCopy('proj-1'); });

    expect(showToast).toHaveBeenCalledWith(catalog['projects.pullFailed']);
  });
});
