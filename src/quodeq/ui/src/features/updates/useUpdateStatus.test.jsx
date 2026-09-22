import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { ApiProvider } from '../../api/ApiContext.jsx';
import { useUpdateStatus } from './useUpdateStatus.js';

describe('useUpdateStatus', () => {
  it('sets status from a successful refresh', async () => {
    const getUpdateStatus = vi.fn().mockResolvedValue({ current: '1.0.0' });
    const { result } = renderHook(() => useUpdateStatus(), {
      wrapper: ({ children }) => <ApiProvider value={{ getUpdateStatus }}>{children}</ApiProvider>,
    });

    await waitFor(() => expect(result.current.status).toEqual({ current: '1.0.0' }));
  });

  it('warns instead of swallowing a refresh failure', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const getUpdateStatus = vi.fn().mockRejectedValue(new Error('status network error'));

    const { result } = renderHook(() => useUpdateStatus(), {
      wrapper: ({ children }) => <ApiProvider value={{ getUpdateStatus }}>{children}</ApiProvider>,
    });

    await waitFor(() => expect(getUpdateStatus).toHaveBeenCalled());
    await waitFor(() => expect(warn).toHaveBeenCalledWith('update status refresh failed:', expect.any(Error)));

    // A rejected refresh must not leave status set to a resolved value.
    expect(result.current.status).toBeNull();
    warn.mockRestore();
  });

  it('explicit refresh() also warns on failure', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const getUpdateStatus = vi.fn()
      .mockResolvedValueOnce({ current: '1.0.0' })
      .mockRejectedValueOnce(new Error('refresh error'));

    const { result } = renderHook(() => useUpdateStatus(), {
      wrapper: ({ children }) => <ApiProvider value={{ getUpdateStatus }}>{children}</ApiProvider>,
    });

    await waitFor(() => expect(result.current.status).toEqual({ current: '1.0.0' }));

    act(() => { result.current.refresh(); });

    await waitFor(() => expect(warn).toHaveBeenCalledWith('update status refresh failed:', expect.any(Error)));
    // Status from the prior successful refresh is left untouched.
    expect(result.current.status).toEqual({ current: '1.0.0' });
    warn.mockRestore();
  });
});
