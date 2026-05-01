import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { withQueryClient } from '../test-utils/withQueryClient.jsx';

vi.mock('../api/index.js', () => ({
  getHealth: vi.fn(),
}));

import { getHealth } from '../api/index.js';
import { useServerHealth } from './useServerHealth.js';

describe('useServerHealth', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reports connected when getHealth resolves', async () => {
    getHealth.mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useServerHealth(), { wrapper: withQueryClient() });
    await waitFor(() => {
      expect(result.current[0]).toBe(true);
    });
  });

  it('reports disconnected when getHealth rejects and no alt port responds', async () => {
    getHealth.mockRejectedValue(new Error('boom'));
    globalThis.fetch.mockRejectedValue(new Error('also boom'));
    const { result } = renderHook(
      () => useServerHealth({ altPorts: [4180], baseUrl: 'http://localhost' }),
      { wrapper: withQueryClient() },
    );
    await waitFor(() => {
      expect(result.current[0]).toBe(false);
    });
  });

  it('exposes setServerConnected for optimistic reconnect', async () => {
    getHealth.mockResolvedValue({ ok: true });
    const { result } = renderHook(() => useServerHealth(), { wrapper: withQueryClient() });
    await waitFor(() => expect(result.current[0]).toBe(true));
    act(() => {
      result.current[1](false);
    });
    expect(result.current[0]).toBe(false);
  });
});
