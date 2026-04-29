import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useServerLogPoll } from './useServerLogPoll.js';

function Probe({ active }) {
  const { logs } = useServerLogPoll(active);
  return <div data-testid="logs">{logs.join('|')}</div>;
}

describe('useServerLogPoll', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    globalThis.fetch = vi.fn();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  function mockFetchOnce(payload) {
    globalThis.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(payload),
    });
  }

  it('does not fetch when inactive', () => {
    render(<Probe active={false} />);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('fetches /api/logs without since on first poll, then formats lines', async () => {
    mockFetchOnce({
      lines: [
        { index: 1, timestamp: '2026-04-29T10:00:05.000Z', line: 'first' },
        { index: 2, timestamp: '2026-04-29T10:00:06.000Z', line: 'second' },
      ],
    });
    render(<Probe active />);
    await act(async () => { await Promise.resolve(); });
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/logs');
    expect(screen.getByTestId('logs')).toHaveTextContent('[10:00:05] first|[10:00:06] second');
  });

  it('passes since on subsequent polls and accumulates lines', async () => {
    mockFetchOnce({ lines: [{ index: 5, timestamp: '2026-04-29T10:00:05.000Z', line: 'a' }] });
    mockFetchOnce({ lines: [{ index: 7, timestamp: '2026-04-29T10:00:07.000Z', line: 'b' }] });
    render(<Probe active />);
    await act(async () => { await Promise.resolve(); });
    await act(async () => { vi.advanceTimersByTime(2000); await Promise.resolve(); });
    expect(globalThis.fetch).toHaveBeenLastCalledWith('/api/logs?since=5');
    expect(screen.getByTestId('logs')).toHaveTextContent('[10:00:05] a|[10:00:07] b');
  });

  it('caps the buffer at 5000 lines, dropping from the front', async () => {
    const lines = Array.from({ length: 5050 }, (_, i) => ({
      index: i, timestamp: '', line: `L${i}`,
    }));
    mockFetchOnce({ lines });
    render(<Probe active />);
    await act(async () => { await Promise.resolve(); });
    const text = screen.getByTestId('logs').textContent;
    const arr = text.split('|');
    expect(arr.length).toBe(5000);
    expect(arr[0]).toBe('L50');
    expect(arr[arr.length - 1]).toBe('L5049');
  });

  it('toggling active off then on resets state', async () => {
    mockFetchOnce({ lines: [{ index: 1, timestamp: '', line: 'old' }] });
    const { rerender } = render(<Probe active />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId('logs')).toHaveTextContent('old');
    await act(async () => { rerender(<Probe active={false} />); });
    expect(screen.getByTestId('logs')).toBeEmptyDOMElement();
    mockFetchOnce({ lines: [{ index: 9, timestamp: '', line: 'new' }] });
    rerender(<Probe active />);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId('logs')).toHaveTextContent('new');
  });
});
