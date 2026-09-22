import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import DesktopSection from './DesktopSection.jsx';

const SUPPORTED_OFF = { supported: true, enabled: false, running: false };
const SUPPORTED_ON = { supported: true, enabled: true, running: true };

const fakeApi = {
  getMenubar: vi.fn(),
  setMenubar: vi.fn(),
};

function renderWithApi() {
  return render(
    <ApiProvider value={fakeApi}>
      <DesktopSection />
    </ApiProvider>,
  );
}

beforeEach(() => {
  fakeApi.getMenubar.mockReset().mockResolvedValue(SUPPORTED_OFF);
  fakeApi.setMenubar.mockReset().mockResolvedValue(SUPPORTED_ON);
});
afterEach(() => { vi.clearAllMocks(); });

describe('DesktopSection', () => {
  it('renders the menu bar toggle when supported', async () => {
    renderWithApi();
    expect(await screen.findByText('Show menu bar icon')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^on$/i })).toBeInTheDocument();
  });

  it('stays hidden when unsupported', async () => {
    fakeApi.getMenubar.mockResolvedValue({ supported: false, enabled: false, running: false });
    renderWithApi();
    await waitFor(() => expect(fakeApi.getMenubar).toHaveBeenCalled());
    expect(screen.queryByText('Show menu bar icon')).not.toBeInTheDocument();
  });

  it('stays hidden when the status request fails', async () => {
    fakeApi.getMenubar.mockRejectedValue(new Error('offline'));
    renderWithApi();
    await waitFor(() => expect(fakeApi.getMenubar).toHaveBeenCalled());
    expect(screen.queryByText('Show menu bar icon')).not.toBeInTheDocument();
  });

  it('turning the toggle on PUTs enabled true', async () => {
    renderWithApi();
    const onButton = await screen.findByRole('button', { name: /^on$/i });
    fireEvent.click(onButton);
    await waitFor(() => expect(fakeApi.setMenubar).toHaveBeenCalledWith(true));
    await waitFor(() => expect(onButton.className).toContain('settings-pill--active'));
  });

  it('reverts optimistic state when the PUT fails', async () => {
    fakeApi.setMenubar.mockRejectedValue(new Error('nope'));
    renderWithApi();
    const onButton = await screen.findByRole('button', { name: /^on$/i });
    fireEvent.click(onButton);
    await waitFor(() => expect(fakeApi.setMenubar).toHaveBeenCalledWith(true));
    await waitFor(() => expect(onButton.className).not.toContain('settings-pill--active'));
  });

  it('logs and surfaces an error when the toggle fails', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    fakeApi.setMenubar.mockRejectedValue(new Error('nope'));
    renderWithApi();
    const onButton = await screen.findByRole('button', { name: /^on$/i });
    fireEvent.click(onButton);
    await waitFor(() => expect(fakeApi.setMenubar).toHaveBeenCalledWith(true));
    expect(await screen.findByText('Could not update the menu bar setting. Try again.')).toBeInTheDocument();
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('[DesktopSection]'),
      expect.any(Error),
    );
  });
});
