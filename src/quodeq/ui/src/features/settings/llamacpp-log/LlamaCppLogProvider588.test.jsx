/**
 * Finding #588 – LlamaCppLogProvider must use request() (30s timeout)
 * instead of raw fetch() for the /api/llamacpp/logs/available probe.
 *
 * Now routed through the api/index.js repository layer
 * (getLlamacppLogAvailable, itself built on request()) and injected via
 * useApi(), so the first assertion pins "the provider calls the injected
 * api function" through an ApiProvider double. The raw-fetch guard is kept
 * verbatim as an independent, belt-and-braces check.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ApiProvider } from '../../../api/ApiContext.jsx';

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

import { LlamaCppLogProvider } from './LlamaCppLogProvider.jsx';
import { LlamaCppLogContext } from './LlamaCppLogContext.js';

function renderProvider(fakeApi) {
  const el = (
    <ApiProvider value={fakeApi}>
      <LlamaCppLogProvider>
        <span data-testid="child">ok</span>
      </LlamaCppLogProvider>
    </ApiProvider>
  );
  return render(el);
}

describe('#588 LlamaCppLogProvider uses request() for availability probe', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('calls the injected getLlamacppLogAvailable() on mount to check availability', async () => {
    const getLlamacppLogAvailable = vi.fn().mockResolvedValue({ available: true });
    renderProvider({ getLlamacppLogAvailable });
    // Let the effect fire (microtask flush).
    await act(async () => { await Promise.resolve(); });
    expect(getLlamacppLogAvailable).toHaveBeenCalled();
  });

  it('does not call raw fetch directly', async () => {
    const getLlamacppLogAvailable = vi.fn().mockResolvedValue({ available: false });
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    renderProvider({ getLlamacppLogAvailable });
    await act(async () => { await Promise.resolve(); });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
