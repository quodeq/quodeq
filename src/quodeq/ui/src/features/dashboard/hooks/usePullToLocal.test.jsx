import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePullToLocal } from './usePullToLocal.js';

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
});
