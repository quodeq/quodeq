import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../../api/index.js', () => ({
  getUpdateStatus: vi.fn(),
  checkForUpdates: vi.fn(),
  setUpdateAutoCheck: vi.fn(() => Promise.resolve({ ok: true })),
}));
import { getUpdateStatus, checkForUpdates, setUpdateAutoCheck } from '../../../api/index.js';
import UpdatesSection from './UpdatesSection.jsx';

const UP_TO_DATE = {
  current: '1.4.0', latest: '1.4.0', update_available: false, is_security: false,
  action_command: 'pipx upgrade quodeq', channel: 'wheel', auto_check_enabled: true,
  last_check_ts: '2026-06-26T10:00:00Z', latest_url: null, download_url: null,
};
const AVAILABLE = { ...UP_TO_DATE, latest: '1.5.0', update_available: true,
  latest_url: 'https://github.com/quodeq/quodeq/releases/tag/v1.5.0' };

beforeEach(() => {
  getUpdateStatus.mockResolvedValue(UP_TO_DATE);
  checkForUpdates.mockResolvedValue(AVAILABLE);
});
afterEach(() => { vi.clearAllMocks(); delete window.pywebview; });

describe('UpdatesSection', () => {
  it('shows the current version and up-to-date state', async () => {
    render(<UpdatesSection />);
    await waitFor(() => expect(screen.getByText(/1\.4\.0/)).toBeInTheDocument());
  });

  it('"Check now" calls the API and surfaces the new version', async () => {
    render(<UpdatesSection />);
    await waitFor(() => expect(getUpdateStatus).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /check/i }));
    await waitFor(() => expect(checkForUpdates).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText(/1\.5\.0/)).toBeInTheDocument());
  });

  it('toggling auto-check calls setUpdateAutoCheck', async () => {
    render(<UpdatesSection />);
    await waitFor(() => expect(getUpdateStatus).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /off/i }));
    await waitFor(() => expect(setUpdateAutoCheck).toHaveBeenCalledWith(false));
  });
});
