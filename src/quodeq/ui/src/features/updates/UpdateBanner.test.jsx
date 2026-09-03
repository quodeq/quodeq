import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../api/index.js', () => ({
  getUpdateStatus: vi.fn(),
  dismissUpdate: vi.fn(() => Promise.resolve({ ok: true })),
  markUpdateDisclosed: vi.fn(() => Promise.resolve({ ok: true })),
  startSelfUpdate: vi.fn(() => Promise.resolve({ ok: true })),
}));
import { getUpdateStatus, dismissUpdate, markUpdateDisclosed, startSelfUpdate } from '../../api/index.js';
import UpdateBanner from './UpdateBanner.jsx';

const AVAILABLE = {
  current: '1.4.0', latest: '1.5.0', update_available: true, is_security: false,
  action_command: 'pipx upgrade quodeq', channel: 'wheel', disclosed: true,
  latest_url: 'https://github.com/quodeq/quodeq/releases/tag/v1.5.0', download_url: null,
};

const FROZEN = {
  ...AVAILABLE,
  action_command: '',
  channel: 'frozen',
  download_url: 'https://example.com/Quodeq-1.5.0-macOS.dmg',
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

  it('calls markUpdateDisclosed when status.disclosed is false', async () => {
    getUpdateStatus.mockResolvedValue({ ...AVAILABLE, disclosed: false });
    render(<UpdateBanner />);
    await waitFor(() => expect(markUpdateDisclosed).toHaveBeenCalledTimes(1));
  });

  it('offers Update and relaunch when self-update is supported', async () => {
    getUpdateStatus.mockResolvedValue({
      ...FROZEN,
      self_update: { supported: true, reason: null, phase: 'idle', percent: 0, error: null },
    });
    render(<UpdateBanner />);
    const button = await screen.findByRole('button', { name: /update and relaunch/i });
    fireEvent.click(button);
    await waitFor(() => expect(startSelfUpdate).toHaveBeenCalledTimes(1));
  });

  it('keeps the plain download button when self-update is unsupported', async () => {
    getUpdateStatus.mockResolvedValue({
      ...FROZEN,
      self_update: { supported: false, reason: 'no_team_id', phase: 'idle', percent: 0, error: null },
    });
    render(<UpdateBanner />);
    await screen.findByRole('button', { name: /download/i });
    expect(screen.queryByRole('button', { name: /update and relaunch/i })).not.toBeInTheDocument();
  });

  it('shows download progress while updating', async () => {
    getUpdateStatus.mockResolvedValue({
      ...FROZEN,
      self_update: { supported: true, reason: null, phase: 'downloading', percent: 42, error: null },
    });
    render(<UpdateBanner />);
    await screen.findByText(/42/);
    expect(screen.queryByRole('button', { name: /update and relaunch/i })).not.toBeInTheDocument();
  });

  it('falls back to the download link when self-update failed', async () => {
    getUpdateStatus.mockResolvedValue({
      ...FROZEN,
      self_update: { supported: true, reason: null, phase: 'error', percent: 0, error: 'boom' },
    });
    render(<UpdateBanner />);
    await screen.findByText(/automatic update failed/i);
    expect(screen.getByRole('button', { name: /download/i })).toBeInTheDocument();
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
