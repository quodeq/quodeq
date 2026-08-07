import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { withQueryClient } from '../test-utils/withQueryClient.jsx';

vi.mock('../api/index.js', () => ({
  getHealth: vi.fn(),
}));

import { getHealth } from '../api/index.js';
import { useServerHealth, altPortCandidates } from './useServerHealth.js';

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

  it('scans the ports the dashboard actually binds', () => {
    // The dashboard walks upward from 7863 when the base port is taken
    // (dashboard/_networking.py), so recovery must probe that range — the
    // old 4180-4183 list pointed at ports quodeq never binds.
    expect(altPortCandidates('')).toEqual([7863, 7864, 7865, 7866, 7867]);
  });

  it('also scans around the port this window is pointed at', () => {
    const candidates = altPortCandidates('9100');
    expect(candidates).toEqual(expect.arrayContaining([7863, 9100, 9101, 9104]));
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
