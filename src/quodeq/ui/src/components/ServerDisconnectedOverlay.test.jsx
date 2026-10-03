import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ServerDisconnectedOverlay from './ServerDisconnectedOverlay.jsx';
import { ApiProvider } from '../api/ApiContext.jsx';
import { t } from '../strings/index.js';

// The retry button used to fire one probe and stay silent on failure, so a
// server that was still down (or wedged for the 30 s request timeout) looked
// like a button that did nothing.

function renderOverlay(getHealth, onReconnect = vi.fn()) {
  render(
    <ApiProvider value={{ getHealth }}>
      <ServerDisconnectedOverlay onReconnect={onReconnect} />
    </ApiProvider>,
  );
  return { onReconnect };
}

describe('ServerDisconnectedOverlay retry', () => {
  it('shows a checking state while the probe is out, then reconnects on success', async () => {
    let resolve;
    const getHealth = vi.fn(() => new Promise((res) => { resolve = res; }));
    const { onReconnect } = renderOverlay(getHealth);
    fireEvent.click(screen.getByRole('button', { name: t('common.retryConnection') }));
    expect(screen.getByRole('button', { name: t('common.checkingConnection') })).toBeDisabled();
    resolve({ ok: true });
    await waitFor(() => expect(onReconnect).toHaveBeenCalledTimes(1));
  });

  it('says the server is still unreachable when the probe fails, and offers to retry again', async () => {
    const getHealth = vi.fn(async () => { throw new Error('ECONNREFUSED'); });
    const { onReconnect } = renderOverlay(getHealth);
    fireEvent.click(screen.getByRole('button', { name: t('common.retryConnection') }));
    expect(await screen.findByText(t('common.stillUnreachable'))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t('common.retryConnection') })).not.toBeDisabled();
    expect(onReconnect).not.toHaveBeenCalled();
  });

  it('probes with a short timeout rather than the default request timeout', () => {
    const getHealth = vi.fn(async () => ({ ok: true }));
    renderOverlay(getHealth);
    fireEvent.click(screen.getByRole('button', { name: t('common.retryConnection') }));
    expect(getHealth).toHaveBeenCalledWith(expect.objectContaining({ timeout: expect.any(Number) }));
    expect(getHealth.mock.calls[0][0].timeout).toBeLessThan(30000);
  });
});
