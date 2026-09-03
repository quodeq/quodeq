import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import UpdatesSection from './UpdatesSection.jsx';

const UP_TO_DATE = {
  current: '1.4.0', latest: '1.4.0', update_available: false, is_security: false,
  action_command: 'pipx upgrade quodeq', channel: 'wheel', auto_check_enabled: true,
  last_check_ts: '2026-06-26T10:00:00Z', latest_url: null, download_url: null,
};
const AVAILABLE = { ...UP_TO_DATE, latest: '1.5.0', update_available: true,
  latest_url: 'https://github.com/quodeq/quodeq/releases/tag/v1.5.0' };

const fakeApi = {
  getUpdateStatus: vi.fn(),
  checkForUpdates: vi.fn(),
  setUpdateAutoCheck: vi.fn(() => Promise.resolve({ ok: true })),
};

function renderWithApi() {
  return render(
    <ApiProvider value={fakeApi}>
      <UpdatesSection />
    </ApiProvider>,
  );
}

beforeEach(() => {
  fakeApi.getUpdateStatus.mockReset().mockResolvedValue(UP_TO_DATE);
  fakeApi.checkForUpdates.mockReset().mockResolvedValue(AVAILABLE);
  fakeApi.setUpdateAutoCheck.mockReset().mockResolvedValue({ ok: true });
});
afterEach(() => { vi.clearAllMocks(); delete window.pywebview; });

describe('UpdatesSection', () => {
  it('shows the current version and up-to-date state', async () => {
    renderWithApi();
    await waitFor(() => expect(screen.getByText(/1\.4\.0/)).toBeInTheDocument());
  });

  it('"Check now" calls the API and surfaces the new version', async () => {
    renderWithApi();
    await waitFor(() => expect(fakeApi.getUpdateStatus).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /check/i }));
    await waitFor(() => expect(fakeApi.checkForUpdates).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText(/1\.5\.0/)).toBeInTheDocument());
  });

  it('toggling auto-check calls setUpdateAutoCheck', async () => {
    renderWithApi();
    await waitFor(() => expect(fakeApi.getUpdateStatus).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /off/i }));
    await waitFor(() => expect(fakeApi.setUpdateAutoCheck).toHaveBeenCalledWith(false));
  });

  it('rolls back the toggle when setUpdateAutoCheck fails, instead of leaving a false "success"', async () => {
    fakeApi.setUpdateAutoCheck.mockRejectedValue(new Error('network'));
    renderWithApi();
    await waitFor(() => expect(fakeApi.getUpdateStatus).toHaveBeenCalled());

    fireEvent.click(screen.getByRole('button', { name: /off/i }));
    await waitFor(() => expect(fakeApi.setUpdateAutoCheck).toHaveBeenCalledWith(false));

    // Optimistic update flips "on" to inactive immediately; once the failed
    // call resolves it should roll back to the previous (active) state.
    await waitFor(() => expect(screen.getByRole('button', { name: /^on$/i })).toHaveClass('settings-pill--active'));
  });
});
