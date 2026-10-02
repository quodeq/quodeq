import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import AccessPanel from './AccessPanel.jsx';

const URL_ = 'https://github.com/o/r.git';

function api(overrides = {}) {
  return {
    probeGit: vi.fn(async () => ({ reachable: true, kind: 'ok' })),
    getGithubAccount: vi.fn(async () => ({ signedIn: false, login: null, method: 'none', ghAvailable: false, ghLoggedIn: false, signInAvailable: true })),
    startDeviceFlow: vi.fn(), getDeviceFlow: vi.fn(), pasteGithubToken: vi.fn(),
    ...overrides,
  };
}

function renderPanel(failure, props = {}, apiOverrides = {}) {
  const a = api(apiOverrides);
  render(<ApiProvider value={a}><AccessPanel failure={failure} url={URL_} onResolved={vi.fn()} onRetry={vi.fn()} {...props} /></ApiProvider>);
  return a;
}

describe('AccessPanel', () => {
  it('auth_required on GitHub shows sign-in, other ways, and the git detail', async () => {
    renderPanel({ kind: 'auth_required', detail: 'fatal: could not read Username', host: 'github.com', isGitHub: true });
    expect(screen.getByText(/can't access this repository yet/i)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /sign in with github/i })).toBeInTheDocument();
    expect(screen.getByText(/other ways to connect/i)).toBeInTheDocument();
    expect(screen.getByText(/could not read Username/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/gh auth login/)).toBeInTheDocument());
  });

  it('not_found on GitHub explains the private-repo case and still offers sign-in', async () => {
    renderPanel({ kind: 'not_found', detail: '', host: 'github.com', isGitHub: true });
    expect(screen.getByText(/no repository at this address/i)).toBeInTheDocument();
    expect(screen.getByText(/private repositories as not found/i)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /sign in with github/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/gh auth login/)).toBeInTheDocument());
  });

  it('gh card appears only when gh is installed and logged out', async () => {
    renderPanel({ kind: 'auth_required', detail: '', host: 'github.com', isGitHub: true }, {}, {
      getGithubAccount: vi.fn(async () => ({ signedIn: false, login: null, method: 'none', ghAvailable: true, ghLoggedIn: false, signInAvailable: true })),
    });
    await waitFor(() => expect(screen.getByText(/gh auth login/)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /check again/i })).toBeInTheDocument();
  });

  it('non-GitHub host shows only the own-git card', () => {
    renderPanel({ kind: 'auth_required', detail: '', host: 'gitlab.example.com', isGitHub: false });
    expect(screen.queryByRole('button', { name: /sign in with github/i })).not.toBeInTheDocument();
    expect(screen.getByText(/use your own git setup/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /test again/i })).toBeInTheDocument();
  });

  it.each([
    ['host_key', /hasn't trusted this server/i],
    ['network', /couldn't reach github.com/i],
    ['timeout', /didn't answer in time|couldn't reach/i],
    ['git_missing', /git isn't installed/i],
    ['git_too_old', /too old/i],
    ['unknown', /couldn't reach this repository/i],
  ])('%s shows guidance and try again, no sign-in', (kind, heading) => {
    const onRetry = vi.fn();
    renderPanel({ kind, detail: '', host: 'github.com', isGitHub: true }, { onRetry });
    expect(screen.getByText(heading)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /sign in with github/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });

  it('test again probes and resolves when reachable', async () => {
    const onResolved = vi.fn();
    const a = renderPanel({ kind: 'auth_required', detail: '', host: 'gitlab.example.com', isGitHub: false }, { onResolved });
    fireEvent.click(screen.getByRole('button', { name: /test again/i }));
    await waitFor(() => expect(onResolved).toHaveBeenCalled());
    expect(a.probeGit).toHaveBeenCalledWith(URL_);
  });

  it('without a client id: no sign-in card, a hint, and the other ways open', async () => {
    renderPanel({ kind: 'auth_required', detail: '', host: 'github.com', isGitHub: true }, {}, {
      getGithubAccount: vi.fn(async () => ({ signedIn: false, login: null, method: 'none', ghAvailable: true, ghLoggedIn: false, signInAvailable: false })),
    });
    expect(await screen.findByText(/sign-in is not set up in this build/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /sign in with github/i })).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/ghp_/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /other ways to connect/i })).toHaveAttribute('aria-expanded', 'true');
  });

  it('renders no sign-in card while the account is still loading', () => {
    renderPanel({ kind: 'auth_required', detail: '', host: 'github.com', isGitHub: true }, {}, {
      getGithubAccount: vi.fn(() => new Promise(() => {})),
    });
    expect(screen.queryByRole('button', { name: /sign in with github/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/sign-in is not set up/i)).not.toBeInTheDocument();
  });

  it('use_https shows the https address as guidance, no sign-in', () => {
    renderPanel({ kind: 'use_https', detail: '', host: 'github.com', isGitHub: true, cloneUrl: 'https://github.com/o/r.git' });
    expect(screen.getByText(/sign-in works over https/i)).toBeInTheDocument();
    expect(screen.getByText('https://github.com/o/r.git')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /sign in with github/i })).not.toBeInTheDocument();
  });

  it('pasting a token calls the api and resolves', async () => {
    const onResolved = vi.fn();
    const a = renderPanel({ kind: 'auth_required', detail: '', host: 'github.com', isGitHub: true }, { onResolved }, {
      pasteGithubToken: vi.fn(async () => ({ login: 'victor' })),
    });
    fireEvent.click(screen.getByText(/other ways to connect/i));
    fireEvent.change(screen.getByPlaceholderText(/ghp_/), { target: { value: 'ghp_x' } });
    fireEvent.click(screen.getByRole('button', { name: /^connect$/i }));
    await waitFor(() => expect(onResolved).toHaveBeenCalled());
    expect(a.pasteGithubToken).toHaveBeenCalledWith('ghp_x');
  });
});
