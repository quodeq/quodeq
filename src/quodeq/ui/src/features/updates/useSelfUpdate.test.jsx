import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { ApiProvider } from '../../api/ApiContext.jsx';
import { useSelfUpdate } from './useSelfUpdate.js';

describe('useSelfUpdate API injection', () => {
  it('resolves getUpdateStatus/startSelfUpdate from the injected ApiProvider, not a static import', async () => {
    const getUpdateStatus = vi.fn().mockResolvedValue({ self_update: { phase: 'idle' } });
    const startSelfUpdate = vi.fn().mockResolvedValue({ ok: true });
    const apiValue = { getUpdateStatus, startSelfUpdate };
    const setStatus = vi.fn();
    const status = { self_update: { phase: 'idle', supported: true, percent: 0 } };

    const { result } = renderHook(() => useSelfUpdate(status, setStatus), {
      wrapper: ({ children }) => <ApiProvider value={apiValue}>{children}</ApiProvider>,
    });

    act(() => { result.current.begin(); });

    // begin() calls startSelfUpdate() then getUpdateStatus() on the injected api,
    // proving useSelfUpdate resolves its calls through ApiContext rather than a
    // static import of api/index.js.
    await waitFor(() => expect(startSelfUpdate).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(getUpdateStatus).toHaveBeenCalledTimes(1));
    expect(setStatus).toHaveBeenCalledWith({ self_update: { phase: 'idle' } });
  });

  it('polls getUpdateStatus from the injected ApiProvider while a phase is active', async () => {
    vi.useFakeTimers();
    try {
      const getUpdateStatus = vi.fn().mockResolvedValue({ self_update: { phase: 'downloading', percent: 50 } });
      const startSelfUpdate = vi.fn();
      const apiValue = { getUpdateStatus, startSelfUpdate };
      const setStatus = vi.fn();
      const status = { self_update: { phase: 'downloading', supported: true, percent: 10 } };

      renderHook(() => useSelfUpdate(status, setStatus), {
        wrapper: ({ children }) => <ApiProvider value={apiValue}>{children}</ApiProvider>,
      });

      await act(async () => { await vi.advanceTimersByTimeAsync(1000); });

      expect(getUpdateStatus).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
