import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useAiClientList } from './useAiClientList.js';

function wrapper(api) {
  return function Wrapper({ children }) {
    return <ApiProvider value={api}>{children}</ApiProvider>;
  };
}

const CONFIGS = { b: { order: 1 }, a: { order: 2 } };

describe('useAiClientList', () => {
  it('lists the clients in provider-config order and reports them to onLoaded', async () => {
    const getAiClients = vi.fn().mockResolvedValue({ clients: [{ id: 'a' }, { id: 'b' }] });
    const onLoaded = vi.fn();
    const { result } = renderHook(() => useAiClientList(CONFIGS, onLoaded), { wrapper: wrapper({ getAiClients }) });
    await waitFor(() => expect(result.current.clients.map((c) => c.id)).toEqual(['b', 'a']));
    expect(result.current.clientsError).toBeNull();
    expect(onLoaded).toHaveBeenCalledTimes(1);
    expect(onLoaded.mock.calls[0][0].map((c) => c.id)).toEqual(['b', 'a']);
  });

  it('works without an onLoaded callback', async () => {
    const getAiClients = vi.fn().mockResolvedValue({});
    const { result } = renderHook(() => useAiClientList(CONFIGS), { wrapper: wrapper({ getAiClients }) });
    await waitFor(() => expect(getAiClients).toHaveBeenCalledTimes(1));
    expect(result.current.clients).toEqual([]);
    expect(result.current.clientsError).toBeNull();
  });

  it('empties the list and sets the load error when the fetch fails', async () => {
    const getAiClients = vi.fn().mockRejectedValue(new Error('down'));
    const onLoaded = vi.fn();
    const { result } = renderHook(() => useAiClientList(CONFIGS, onLoaded), { wrapper: wrapper({ getAiClients }) });
    await waitFor(() => expect(result.current.clientsError).toMatch(/couldn.t load your AI providers/i));
    expect(result.current.clients).toEqual([]);
    expect(onLoaded).not.toHaveBeenCalled();
  });
});
