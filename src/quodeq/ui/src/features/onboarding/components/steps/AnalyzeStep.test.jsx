import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import AnalyzeStep from './AnalyzeStep.jsx';
import { useWizardState } from '../../hooks/useWizardState.js';
import { STEP_ANALYZE } from '../../wizardSteps.js';
import { ApiProvider } from '../../../../api/ApiContext.jsx';

// The folder browser is its own modal with its own fetches; here a pick
// resolves with whatever the test queued.
const picks = vi.hoisted(() => ({ next: null }));
vi.mock('../../../dashboard/hooks/useFolderPicker.jsx', () => ({
  useFolderPicker: () => ({ browseFolder: async () => picks.next, picker: null }),
}));
vi.mock('../../../github-access/components/AccessPanel.jsx', () => ({
  default: ({ failure }) => <div data-testid="access-panel">{failure.kind}</div>,
}));

// The api the add talks to: a url probes reachable and clones as a job
// (202), a folder registers at once.
function fakeApi(extra = {}) {
  return {
    probeGit: vi.fn(async () => ({ reachable: true })),
    registerProject: vi.fn(async ({ repo }) => (repo.startsWith('/') ? { projectId: 'p-folder', scanData: {} } : { started: true, repo, dest: '' })),
    getCloneStatus: vi.fn(async () => null),
    getProjectInfo: vi.fn(),
    getProjectScan: vi.fn(),
    ...extra,
  };
}

// The step against a live wizard state, the way OnboardingStepSwitch mounts it.
function Step(props) {
  const wizard = useWizardState({ initial: { step: STEP_ANALYZE } });
  return <AnalyzeStep state={wizard.state} actions={wizard} onAdded={() => {}} {...props} />;
}

function renderAdd({ api = fakeApi(), ...props } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><ApiProvider value={api}><Step {...props} /></ApiProvider></QueryClientProvider>);
  return { api };
}

describe('AnalyzeStep (the add panel)', () => {
  let user;
  beforeEach(() => {
    localStorage.clear();
    picks.next = null;
    user = userEvent.setup();
  });

  it('one field and a local folder button; add is disabled until something is typed', () => {
    renderAdd();
    expect(screen.getByText('add project')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'repository' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'local folder' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'add' })).toBeDisabled();
    expect(screen.queryByText('Reviewed by')).toBeNull();
    expect(screen.queryByText('Against')).toBeNull();
  });

  it('a typed url shows the working copy and add posts the clone and hands over as cloning', async () => {
    const onAdded = vi.fn();
    const { api } = renderAdd({ onAdded });
    await user.type(screen.getByRole('textbox', { name: 'repository' }), 'https://github.com/acme/billing.git');
    expect(screen.getByText(/quodeq keeps a working copy in .*quodeq\/repos\/billing/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'add' }));
    await waitFor(() => expect(onAdded).toHaveBeenCalledWith({ projectId: null, cloning: true }));
    expect(api.probeGit).toHaveBeenCalledWith('https://github.com/acme/billing.git');
    expect(api.registerProject).toHaveBeenCalledWith({ repo: 'https://github.com/acme/billing.git' });
  });

  it('local folder fills the field with the picked path, hides the working copy, and add registers at once', async () => {
    const onAdded = vi.fn();
    picks.next = '/Users/me/code/app';
    const { api } = renderAdd({ onAdded });
    await user.click(screen.getByRole('button', { name: 'local folder' }));
    expect(await screen.findByDisplayValue('/Users/me/code/app')).toBeInTheDocument();
    expect(screen.queryByText(/quodeq keeps a working copy/)).toBeNull();
    expect(screen.getByText('a local folder is evaluated in place, nothing is copied.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'add' }));
    await waitFor(() => expect(onAdded).toHaveBeenCalledWith({ projectId: 'p-folder', cloning: false }));
    expect(api.registerProject).toHaveBeenCalledWith({ repo: '/Users/me/code/app' });
    expect(api.probeGit).not.toHaveBeenCalled();
  });

  it('a typed path is a folder too', async () => {
    renderAdd();
    await user.type(screen.getByRole('textbox', { name: 'repository' }), '/Users/me/code/app');
    expect(screen.getByText('a local folder is evaluated in place, nothing is copied.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'add' })).toBeEnabled();
  });

  it('an unreachable url opens the access panel in place and keeps the panel', async () => {
    const onAdded = vi.fn();
    const api = fakeApi({ probeGit: vi.fn(async () => ({ reachable: false, kind: 'auth_required', host: 'github.com', isGitHub: true })) });
    renderAdd({ api, onAdded });
    await user.type(screen.getByRole('textbox', { name: 'repository' }), 'https://github.com/acme/private.git');
    await user.click(screen.getByRole('button', { name: 'add' }));
    expect(await screen.findByTestId('access-panel')).toHaveTextContent('auth_required');
    expect(onAdded).not.toHaveBeenCalled();
    expect(api.registerProject).not.toHaveBeenCalled();
  });

  it('a refused folder shows the error with retry; a changed working-copy root is sent on the next add', async () => {
    const err = Object.assign(new Error('bad'), { status: 400, code: 'DEST_EXISTS' });
    const api = fakeApi({ registerProject: vi.fn().mockRejectedValueOnce(err).mockResolvedValueOnce({ started: true, repo: 'x' }) });
    renderAdd({ api });
    await user.type(screen.getByRole('textbox', { name: 'repository' }), 'https://github.com/acme/billing.git');
    await user.click(screen.getByRole('button', { name: 'add' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    picks.next = '/Volumes/work';
    await user.click(screen.getByRole('button', { name: 'change where the working copy goes' }));
    expect(await screen.findByText(/quodeq keeps a working copy in \/Volumes\/work\/billing/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'retry' }));
    await waitFor(() => expect(api.registerProject).toHaveBeenCalledTimes(2));
    expect(api.registerProject).toHaveBeenLastCalledWith({ repo: 'https://github.com/acme/billing.git', cloneDest: '/Volumes/work' });
  });
});
