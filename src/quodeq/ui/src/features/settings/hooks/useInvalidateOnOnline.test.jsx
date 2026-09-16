import { describe, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useInvalidateOnOnline } from './useInvalidateOnOnline.js';

function wrapper(client) {
  return ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const KEY = ['settings', 'models'];

describe('useInvalidateOnOnline', () => {
  it('invalidates the key only on the transition into online', () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { rerender } = renderHook(({ status }) => useInvalidateOnOnline(status, KEY), {
      wrapper: wrapper(client),
      initialProps: { status: 'offline' },
    });
    expect(spy).not.toHaveBeenCalled();
    rerender({ status: 'online' });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith({ queryKey: KEY });
    rerender({ status: 'online' });
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('does not invalidate when mounted already online', () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, 'invalidateQueries');
    renderHook(() => useInvalidateOnOnline('online', KEY), { wrapper: wrapper(client) });
    expect(spy).not.toHaveBeenCalled();
  });

  it('treats an undefined status as offline', () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, 'invalidateQueries');
    const { rerender } = renderHook(({ status }) => useInvalidateOnOnline(status, KEY), {
      wrapper: wrapper(client),
      initialProps: { status: undefined },
    });
    rerender({ status: 'online' });
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
