import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import AnalyzeStep from './AnalyzeStep.jsx';
import { useWizardState } from '../../hooks/useWizardState.js';
import { STEP_ANALYZE } from '../../wizardSteps.js';
import { ApiProvider } from '../../../../api/ApiContext.jsx';
import { projectsKeys } from '../../../../api/queryKeys.js';
import { SYNC_PHASE } from '../../../../vocab/syncPhase.js';

vi.mock('../../../../api/index.js', () => ({ getProviderConfigs: vi.fn(async () => ({})) }));
vi.mock('../../../settings/components/ProviderTabs.jsx', () => ({
  default: () => <div data-testid="provider-tabs-stub" />,
}));
// The folder browser is its own modal with its own fetches; here a pick
// resolves with whatever the test queued.
const picks = vi.hoisted(() => ({ next: null }));
vi.mock('../../../dashboard/hooks/useFolderPicker.jsx', () => ({
  useFolderPicker: () => ({ browseFolder: async () => picks.next, picker: null }),
}));

const standards = [{ id: 'default', name: 'quodeq default standard', dimensions: ['security', 'maintainability', 'performance', 'reliability', 'usability', 'flexibility'] }];
const claudeDetected = async () => [{ id: 'claude-code', classification: 'cli', detected: true, defaultModel: 'claude-sonnet-5-5' }];

function writeActiveProviderState({ id, model }) {
  localStorage.setItem('cc-active-provider', id);
  localStorage.setItem(`cc-${id}-model`, model);
}

const IDLE_SLOT = { state: 'idle', kind: 'clone', phase: null, repo: '', finishedAt: null };

// The api the launch talks to: a url probes reachable and clones as a job
// (202), a folder registers at once; the clone slot starts idle.
function fakeApi(extra = {}) {
  return {
    probeGit: vi.fn(async () => ({ reachable: true })),
    registerProject: vi.fn(async ({ repo }) => (repo.startsWith('/') ? { projectId: 'p-folder', scanData: {} } : { started: true, repo, dest: '' })),
    getCloneStatus: vi.fn(async () => IDLE_SLOT),
    getProjectInfo: vi.fn(),
    getProjectScan: vi.fn(),
    ...extra,
  };
}

// The step against a live wizard state, the way OnboardingStepSwitch mounts it.
function Step({ standardsList, ...props }) {
  const wizard = useWizardState({ initial: { step: STEP_ANALYZE } });
  return <AnalyzeStep state={wizard.state} actions={wizard} standards={standardsList} onLaunch={() => {}} {...props} />;
}

function renderAnalyze({ api = fakeApi(), standardsList = standards, ...props } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><ApiProvider value={api}><Step standardsList={standardsList} {...props} /></ApiProvider></QueryClientProvider>);
  return { api, qc };
}

describe('AnalyzeStep', () => {
  let user;
  beforeEach(() => {
    localStorage.clear();
    picks.next = null;
    user = userEvent.setup();
  });

  it('first run: detected provider is recommended, default standard shown, run disabled until a repo is typed', async () => {
    renderAnalyze({ detect: claudeDetected });
    expect(await screen.findByText('found · recommended')).toBeInTheDocument();
    expect(screen.getByText('Claude Code')).toBeInTheDocument();
    expect(screen.getByText('quodeq default standard')).toBeInTheDocument();
    expect(screen.getByText(/security, maintainability, performance/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'scan and run' })).toBeDisabled();
    await user.type(screen.getByRole('textbox', { name: 'repository' }), 'https://github.com/acme/billing.git');
    expect(screen.getByText(/quodeq keeps a working copy in .*quodeq\/repos\/billing/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'scan and run' })).toBeEnabled();
  });

  it('returning user: one summary line, the drawer stays closed until change', async () => {
    writeActiveProviderState({ id: 'claude', model: 'claude-sonnet-5-5' });
    renderAnalyze({ detect: async () => [] });
    expect(await screen.findByText('reviewed by Claude Code · against quodeq default standard')).toBeInTheDocument();
    expect(screen.queryByText('Reviewed by')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'change' }));
    expect(screen.getByText('Reviewed by')).toBeInTheDocument();
  });

  it('no model found offers set one up, which opens the provider tabs', async () => {
    renderAnalyze({ detect: async () => [] });
    expect(await screen.findByText('no model found on this machine')).toBeInTheDocument();
    expect(screen.queryByTestId('provider-tabs-stub')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'set one up' }));
    expect(screen.getByTestId('provider-tabs-stub')).toBeInTheDocument();
  });

  it('the folder source hides the working-copy note, registers at once and launches', async () => {
    const onLaunch = vi.fn();
    picks.next = '/Users/me/code/app';
    const { api } = renderAnalyze({ detect: claudeDetected, onLaunch });
    await screen.findByText('found · recommended');
    await user.click(screen.getByRole('radio', { name: 'choose a local folder' }));
    await user.click(screen.getByRole('button', { name: 'choose a folder' }));
    expect(await screen.findByText('/Users/me/code/app')).toBeInTheDocument();
    expect(screen.queryByText(/quodeq keeps a working copy/)).toBeNull();
    await user.click(screen.getByRole('button', { name: 'scan and run' }));
    await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
    expect(api.registerProject).toHaveBeenCalledWith({ repo: '/Users/me/code/app' });
    expect(api.probeGit).not.toHaveBeenCalled();
    expect(onLaunch.mock.calls[0][0]).toEqual({ projectId: 'p-folder', standardIds: ['default'] });
  });

  it('a changed working-copy root is sent as cloneDest; the default is not', async () => {
    const { api, qc } = renderAnalyze({ detect: claudeDetected });
    await screen.findByText('found · recommended');
    await user.type(screen.getByRole('textbox', { name: 'repository' }), 'https://github.com/acme/billing.git');
    await user.click(screen.getByRole('button', { name: 'scan and run' }));
    await waitFor(() => expect(api.registerProject).toHaveBeenCalledTimes(1));
    expect(api.registerProject).toHaveBeenLastCalledWith({ repo: 'https://github.com/acme/billing.git' });

    // The clone failed: the error row's retry posts again, with the new root.
    qc.setQueryData(projectsKeys.clone(), { ...IDLE_SLOT, state: 'error', phase: SYNC_PHASE.ERROR, repo: 'https://github.com/acme/billing.git', code: 'DEST_EXISTS', finishedAt: 1700000000000 });
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    picks.next = '/Volumes/work';
    await user.click(screen.getByRole('button', { name: 'change where the working copy goes' }));
    expect(await screen.findByText(/quodeq keeps a working copy in \/Volumes\/work\/billing/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'retry' }));
    await waitFor(() => expect(api.registerProject).toHaveBeenCalledTimes(2));
    expect(api.registerProject).toHaveBeenLastCalledWith({ repo: 'https://github.com/acme/billing.git', cloneDest: '/Volumes/work' });
    expect(localStorage.getItem('quodeq.lastCloneRoot')).toBe('/Volumes/work');
  });

  it('a url shows the clone in the panel and scan and run waits for it', async () => {
    const { qc } = renderAnalyze({ detect: claudeDetected });
    await screen.findByText('found · recommended');
    await user.type(screen.getByRole('textbox', { name: 'repository' }), 'https://github.com/acme/billing.git');
    await user.click(screen.getByRole('button', { name: 'scan and run' }));
    qc.setQueryData(projectsKeys.clone(), { ...IDLE_SLOT, state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 45, bytes: 12582912, repo: 'https://github.com/acme/billing.git' });
    expect(await screen.findByText('cloning · 45% · 12.0 MB')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'scan and run' })).toBeDisabled();
  });

  it('after set one up and done, the summary reads the configured provider and run is enabled', async () => {
    renderAnalyze({ detect: async () => [] });
    await user.click(await screen.findByRole('button', { name: 'set one up' }));
    writeActiveProviderState({ id: 'claude', model: 'claude-sonnet-5-5' });
    await user.click(screen.getByRole('button', { name: 'done' }));
    await user.type(screen.getByRole('textbox', { name: 'repository' }), 'https://github.com/acme/billing.git');
    expect(screen.getByText('reviewed by Claude Code · against quodeq default standard')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'scan and run' })).toBeEnabled();
  });

  it('a returning user sees no summary until the standards load', async () => {
    writeActiveProviderState({ id: 'claude', model: 'claude-sonnet-5-5' });
    renderAnalyze({ detect: async () => [], standardsList: [] });
    await waitFor(() => expect(screen.getByRole('button', { name: 'scan and run' })).toBeDisabled());
    expect(screen.queryByText(/reviewed by/)).toBeNull();
  });
});
