import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ApiContext } from '../../../api/ApiContext.jsx';
import { useOllamaServerStatus } from './useOllamaServerStatus.js';

function Probe() {
  const result = useOllamaServerStatus();
  return (
    <div>
      <div data-testid="status">{result?.status ?? 'pending'}</div>
      <div data-testid="address">{result?.address ?? '-'}</div>
    </div>
  );
}

function renderWithApi(getOllamaStatus) {
  return render(
    <ApiContext.Provider value={{ getOllamaStatus }}>
      <Probe />
    </ApiContext.Provider>
  );
}

describe('useOllamaServerStatus', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it('returns null until the first poll resolves', () => {
    const get = vi.fn(() => new Promise(() => {}));
    renderWithApi(get);
    expect(screen.getByTestId('status')).toHaveTextContent('pending');
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('returns online status with address when poll succeeds', async () => {
    const get = vi.fn().mockResolvedValue({ running: true, address: 'localhost:11434' });
    renderWithApi(get);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId('status')).toHaveTextContent('online');
    expect(screen.getByTestId('address')).toHaveTextContent('localhost:11434');
  });

  it('returns offline status when running=false', async () => {
    const get = vi.fn().mockResolvedValue({ running: false });
    renderWithApi(get);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId('status')).toHaveTextContent('offline');
  });

  it('returns offline when the API call rejects', async () => {
    const get = vi.fn().mockRejectedValue(new Error('boom'));
    renderWithApi(get);
    await act(async () => { await Promise.resolve(); });
    expect(screen.getByTestId('status')).toHaveTextContent('offline');
  });
});
