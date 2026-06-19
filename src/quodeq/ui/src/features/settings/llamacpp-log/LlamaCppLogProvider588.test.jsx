/**
 * Finding #588 – LlamaCppLogProvider must use request() (30s timeout)
 * instead of raw fetch() for the /api/llamacpp/logs/available probe.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Mock request so we can detect it is called.
vi.mock('../../../api/request.js', () => ({
  BASE: '/api',
  request: vi.fn(),
}));

// Mock the SSE stream hook so LlamaCppLogProvider doesn't open EventSource.
vi.mock('./useLlamaCppLogStream.js', () => ({
  useLlamaCppLogStream: () => ({ logs: [], status: 'idle' }),
}));

// Minimal SidePaneContext mock.
vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({
    addWindow: vi.fn(),
    removeWindow: vi.fn(),
    replaceWindow: vi.fn(),
    hasWindow: () => false,
    windows: [],
  }),
}));

import { request } from '../../../api/request.js';
import { LlamaCppLogProvider } from './LlamaCppLogProvider.jsx';
import { LlamaCppLogContext } from './LlamaCppLogContext.js';

function renderProvider() {
  const el = (
    <LlamaCppLogProvider>
      <span data-testid="child">ok</span>
    </LlamaCppLogProvider>
  );
  return render(el);
}

describe('#588 LlamaCppLogProvider uses request() for availability probe', () => {
  beforeEach(() => {
    request.mockReset();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls request() on mount to check availability', async () => {
    request.mockResolvedValue({ available: true });
    renderProvider();
    // Let the effect fire (microtask flush).
    await act(async () => { await Promise.resolve(); });
    expect(request).toHaveBeenCalled();
    const [path] = request.mock.calls[0];
    expect(path).toContain('/llamacpp/logs/available');
  });

  it('does not call raw fetch directly', async () => {
    request.mockResolvedValue({ available: false });
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    renderProvider();
    await act(async () => { await Promise.resolve(); });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
