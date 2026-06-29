import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../api/index.js', () => ({
  getUpdateStatus: vi.fn(),
  dismissUpdate: vi.fn(() => Promise.resolve({ ok: true })),
  markUpdateDisclosed: vi.fn(() => Promise.resolve({ ok: true })),
}));
import { getUpdateStatus, dismissUpdate } from '../../api/index.js';
import UpdateBanner from './UpdateBanner.jsx';

const AVAILABLE = {
  current: '1.4.0', latest: '1.5.0', update_available: true, is_security: false,
  action_command: 'pipx upgrade quodeq', channel: 'wheel', disclosed: true,
  latest_url: 'https://github.com/quodeq/quodeq/releases/tag/v1.5.0', download_url: null,
};

afterEach(() => { vi.clearAllMocks(); });

describe('UpdateBanner', () => {
  it('renders nothing when up to date', async () => {
    getUpdateStatus.mockResolvedValue({ ...AVAILABLE, update_available: false, disclosed: true });
    const { container } = render(<UpdateBanner />);
    await waitFor(() => expect(getUpdateStatus).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the version delta when an update is available', async () => {
    getUpdateStatus.mockResolvedValue(AVAILABLE);
    render(<UpdateBanner />);
    await waitFor(() => expect(screen.getByText(/1\.5\.0/)).toBeInTheDocument());
  });

  it('dismiss calls dismissUpdate with the latest version and hides', async () => {
    getUpdateStatus.mockResolvedValue(AVAILABLE);
    render(<UpdateBanner />);
    await waitFor(() => expect(screen.getByText(/1\.5\.0/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));
    await waitFor(() => expect(dismissUpdate).toHaveBeenCalledWith('1.5.0'));
    expect(screen.queryByText(/1\.5\.0/)).not.toBeInTheDocument();
  });
});
