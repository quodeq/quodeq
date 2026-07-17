import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import SharedRepoSection from './SharedRepoSection.jsx';

function makeFakeApi(overrides = {}) {
  return {
    getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    connectShared: vi.fn(async (url) => ({ configured: true, url })),
    disconnectShared: vi.fn(async () => ({ configured: false })),
    ...overrides,
  };
}

function renderWithApi(fakeApi, props = {}) {
  const QC = withQueryClient();
  return render(
    <QC>
      <ApiProvider value={fakeApi}><SharedRepoSection {...props} /></ApiProvider>
    </QC>
  );
}

describe('SharedRepoSection', () => {
  it('renders with not configured when status returns configured: false', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    });

    renderWithApi(fakeApi);

    await waitFor(() => {
      expect(screen.getByText(/not configured/i)).toBeTruthy();
    });
  });

  it('renders with current URL when status returns configured: true', async () => {
    const testUrl = 'https://github.com/team/results.git';
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: testUrl })),
    });

    renderWithApi(fakeApi);

    await waitFor(() => {
      expect(screen.getByDisplayValue(testUrl)).toBeTruthy();
    });
  });

  it('calls connectShared with the typed URL on save', async () => {
    const newUrl = 'https://github.com/team/results.git';
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
      connectShared: vi.fn(async (url) => ({ configured: true, url })),
    });

    const user = userEvent.setup();
    renderWithApi(fakeApi);

    // Wait for component to load
    await waitFor(() => {
      expect(screen.getByText(/repository url/i)).toBeTruthy();
    });

    const input = screen.getByRole('textbox', { name: /repository url/i });
    await user.clear(input);
    await user.type(input, newUrl);

    const saveButton = screen.getByRole('button', { name: /save/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(fakeApi.connectShared).toHaveBeenCalledWith(newUrl);
    });
  });

  it('updates the displayed URL after successful save', async () => {
    const newUrl = 'https://github.com/team/results.git';
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
      connectShared: vi.fn(async (url) => ({ configured: true, url })),
    });

    const user = userEvent.setup();
    renderWithApi(fakeApi);

    await waitFor(() => {
      expect(screen.getByText(/repository url/i)).toBeTruthy();
    });

    const input = screen.getByRole('textbox', { name: /repository url/i });
    await user.clear(input);
    await user.type(input, newUrl);

    const saveButton = screen.getByRole('button', { name: /save/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(screen.getByDisplayValue(newUrl)).toBeTruthy();
    });
  });

  it('displays error message on failed save', async () => {
    const errorMsg = 'not a valid git repository';
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
      connectShared: vi.fn(async () => { throw new Error(errorMsg); }),
    });

    const user = userEvent.setup();
    renderWithApi(fakeApi);

    await waitFor(() => {
      expect(screen.getByText(/repository url/i)).toBeTruthy();
    });

    const input = screen.getByRole('textbox', { name: /repository url/i });
    await user.clear(input);
    await user.type(input, 'https://example.com/invalid.git');

    const saveButton = screen.getByRole('button', { name: /save/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(screen.getByText(new RegExp(errorMsg, 'i'))).toBeTruthy();
    });
  });

  it('shows disconnect button only when configured', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    });

    renderWithApi(fakeApi);

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /disconnect/i })).toBeFalsy();
    });
  });

  it('shows disconnect button when configured', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
    });

    renderWithApi(fakeApi);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /disconnect/i })).toBeTruthy();
    });
  });

  it('calls disconnectShared when disconnect confirm is accepted', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      disconnectShared: vi.fn(async () => ({ configured: false })),
    });

    const user = userEvent.setup();
    renderWithApi(fakeApi);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /disconnect/i })).toBeTruthy();
    });

    const disconnectButton = screen.getByRole('button', { name: /disconnect/i });
    await user.click(disconnectButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /yes/i })).toBeTruthy();
    });

    const confirmButton = screen.getByRole('button', { name: /yes/i });
    await user.click(confirmButton);

    await waitFor(() => {
      expect(fakeApi.disconnectShared).toHaveBeenCalled();
    });
  });

  it('cancels disconnect confirm when no is clicked', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      disconnectShared: vi.fn(async () => ({ configured: false })),
    });

    const user = userEvent.setup();
    renderWithApi(fakeApi);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /disconnect/i })).toBeTruthy();
    });

    const disconnectButton = screen.getByRole('button', { name: /disconnect/i });
    await user.click(disconnectButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /no/i })).toBeTruthy();
    });

    const cancelButton = screen.getByRole('button', { name: /no/i });
    await user.click(cancelButton);

    expect(fakeApi.disconnectShared).not.toHaveBeenCalled();
  });

  // Important 4 (final whole-branch review): a currently-'shared' selection
  // has nowhere left to resolve once the repo is disconnected. SharedRepoSection
  // doesn't own project-selection state itself -- it calls an onDisconnected
  // callback so App.jsx can reset the selection at the seam that actually
  // knows about it.
  it('calls onDisconnected after a successful disconnect', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      disconnectShared: vi.fn(async () => ({ configured: false })),
    });
    const onDisconnected = vi.fn();
    const user = userEvent.setup();
    renderWithApi(fakeApi, { onDisconnected });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /disconnect/i })).toBeTruthy();
    });
    await user.click(screen.getByRole('button', { name: /disconnect/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /yes/i })).toBeTruthy());
    await user.click(screen.getByRole('button', { name: /yes/i }));

    await waitFor(() => expect(onDisconnected).toHaveBeenCalledTimes(1));
  });

  it('does not call onDisconnected when disconnect is cancelled', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
    });
    const onDisconnected = vi.fn();
    const user = userEvent.setup();
    renderWithApi(fakeApi, { onDisconnected });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /disconnect/i })).toBeTruthy();
    });
    await user.click(screen.getByRole('button', { name: /disconnect/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /no/i })).toBeTruthy());
    await user.click(screen.getByRole('button', { name: /no/i }));

    expect(onDisconnected).not.toHaveBeenCalled();
  });
});
