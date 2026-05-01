import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useServerLogPoll } from './useServerLogPoll.js';

function Probe({ active }) {
  const { logs } = useServerLogPoll(active);
  return <div data-testid="logs">{logs.join('|')}</div>;
}

function renderProbe(active) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <Probe active={active} />
    </QueryClientProvider>
  );
}

describe('useServerLogPoll', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockFetchOnce(payload) {
    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(payload),
    });
  }

  it('does not fetch when inactive', () => {
    renderProbe(false);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('fetches /api/logs without since on first poll, then formats lines', async () => {
    mockFetchOnce({
      lines: [
        { index: 1, timestamp: '2026-04-29T10:00:05.000Z', line: 'first' },
        { index: 2, timestamp: '2026-04-29T10:00:06.000Z', line: 'second' },
      ],
    });
    // Subsequent polls return empty so the test stays deterministic.
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ lines: [] }),
    });
    renderProbe(true);
    await waitFor(() => {
      expect(screen.getByTestId('logs')).toHaveTextContent('[10:00:05] first|[10:00:06] second');
    });
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/logs');
  });

  it('passes since on subsequent polls and accumulates lines', async () => {
    mockFetchOnce({ lines: [{ index: 5, timestamp: '2026-04-29T10:00:05.000Z', line: 'a' }] });
    mockFetchOnce({ lines: [{ index: 7, timestamp: '2026-04-29T10:00:07.000Z', line: 'b' }] });
    // Padding for any extra polls before assertion.
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ lines: [] }),
    });
    renderProbe(true);
    await waitFor(() => {
      expect(screen.getByTestId('logs')).toHaveTextContent('[10:00:05] a|[10:00:07] b');
    }, { timeout: 4000 });
    // The second poll passes since=5 (the cursor advanced after 'a' arrived).
    expect(globalThis.fetch).toHaveBeenNthCalledWith(2, '/api/logs?since=5');
  });

  it('caps the buffer at 5000 lines, dropping from the front', async () => {
    const lines = Array.from({ length: 5050 }, (_, i) => ({
      index: i, timestamp: '', line: `L${i}`,
    }));
    mockFetchOnce({ lines });
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ lines: [] }),
    });
    renderProbe(true);
    await waitFor(() => {
      const text = screen.getByTestId('logs').textContent;
      const arr = text.split('|');
      expect(arr.length).toBe(5000);
      expect(arr[0]).toBe('L50');
      expect(arr[arr.length - 1]).toBe('L5049');
    });
  });

  it('toggling active off then on resets state', async () => {
    mockFetchOnce({ lines: [{ index: 1, timestamp: '', line: 'old' }] });
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ lines: [] }),
    });
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0, staleTime: 0 },
        mutations: { retry: false },
      },
    });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <Probe active />
      </QueryClientProvider>
    );
    await waitFor(() => {
      expect(screen.getByTestId('logs')).toHaveTextContent('old');
    });
    await act(async () => {
      rerender(
        <QueryClientProvider client={client}>
          <Probe active={false} />
        </QueryClientProvider>
      );
    });
    expect(screen.getByTestId('logs')).toBeEmptyDOMElement();

    globalThis.fetch.mockReset();
    mockFetchOnce({ lines: [{ index: 9, timestamp: '', line: 'new' }] });
    globalThis.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ lines: [] }),
    });
    rerender(
      <QueryClientProvider client={client}>
        <Probe active />
      </QueryClientProvider>
    );
    await waitFor(() => {
      expect(screen.getByTestId('logs')).toHaveTextContent('new');
    });
  });

  it('handles fetch rejection without throwing', async () => {
    globalThis.fetch.mockRejectedValue(new Error('boom'));
    renderProbe(true);
    // Wait long enough for at least one poll; logs should remain empty.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId('logs')).toBeEmptyDOMElement();
  });
});
