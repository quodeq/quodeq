import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { makeFakeApi, renderWithApi } from './_sharedRepoSection.fixtures.jsx';

describe('SharedRepoSection access panel', () => {
  it('an ACCESS_ failure renders the panel and resolving retries the connect', async () => {
    const err = Object.assign(new Error('x'), { status: 400, code: 'ACCESS_AUTH_REQUIRED', body: { kind: 'auth_required', detail: 'denied', host: 'github.com', isGitHub: true } });
    const connectShared = vi.fn().mockRejectedValueOnce(err).mockResolvedValueOnce({ configured: true, url: 'https://github.com/t/r.git' });
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
      connectShared,
      probeGit: vi.fn(async () => ({ reachable: true, kind: 'ok' })),
      getGithubAccount: vi.fn(async () => ({ ghAvailable: false, ghLoggedIn: false, signInAvailable: true })),
    });
    renderWithApi(fakeApi);
    await waitFor(() => screen.getByText(/repository url/i));
    fireEvent.change(screen.getByLabelText(/shared repository url/i), { target: { value: 'https://github.com/t/r.git' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(screen.getByText(/can't access this repository yet/i)).toBeInTheDocument());
    expect(screen.getByText(/denied/)).toBeInTheDocument();
    // "test again" lives under other ways; open it and resolve.
    fireEvent.click(screen.getByText(/other ways to connect/i));
    fireEvent.click(screen.getByRole('button', { name: /test again/i }));
    await waitFor(() => expect(connectShared).toHaveBeenCalledTimes(2));
  });

  it('ACCESS_USE_HTTPS shows the https address the token can reach', async () => {
    const body = { kind: 'use_https', detail: '', host: 'github.com', isGitHub: true, cloneUrl: 'https://github.com/t/r.git' };
    const err = Object.assign(new Error('x'), { status: 400, code: 'ACCESS_USE_HTTPS', body });
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
      connectShared: vi.fn().mockRejectedValueOnce(err),
      getGithubAccount: vi.fn(async () => ({ ghAvailable: false, ghLoggedIn: false, signInAvailable: true })),
    });
    renderWithApi(fakeApi);
    await waitFor(() => screen.getByText(/repository url/i));
    fireEvent.change(screen.getByLabelText(/shared repository url/i), { target: { value: 'git@github.com:t/r.git' } });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    await waitFor(() => expect(screen.getByText(/sign-in works over https/i)).toBeInTheDocument());
    expect(screen.getByText('https://github.com/t/r.git')).toBeInTheDocument();
  });
});
