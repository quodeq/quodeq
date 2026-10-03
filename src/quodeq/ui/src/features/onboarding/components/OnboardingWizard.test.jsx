import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import OnboardingWizard from './OnboardingWizard.jsx';
import { STEP_REPO_SCAN } from '../wizardSteps.js';
import { WIZARD_SOURCE } from '../onboardingVocab.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';

vi.mock('../hooks/useProviderDetection.js', () => ({
  useProviderDetection: () => ({ status: 'detected', preselection: { id: 'codex-cli', classification: 'cli', model: 'gpt-5.2-codex' } }),
}));

const shared = vi.hoisted(() => ({ status: { configured: false } }));

vi.mock('../../../api/index.js', () => ({
  registerProject: vi.fn().mockResolvedValue({ projectId: 'uuid-9', scanData: { total_files: 7, languages: { py: 7 }, branches: ['main'], modules: [] } }),
  listStandards: vi.fn().mockResolvedValue([{ id: 'std-a', name: 'Security 101', description: 'Common checks' }]),
  getProjectInfo: vi.fn().mockResolvedValue({ id: 'uuid-9', runsCount: 0 }),
  getProjectScan: vi.fn().mockResolvedValue({ total_files: 7, languages: { py: 7 }, branches: ['main'], modules: [] }),
  probeGit: vi.fn().mockResolvedValue({ reachable: true, kind: 'ok' }),
  getSharedStatus: vi.fn(async () => shared.status),
  sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
}));

const SKIP_FLAG = 'quodeq_onboarding_skipped';

function renderWizard(entry, handlers = {}) {
  const props = { onClose: vi.fn(), onLaunch: vi.fn(), onGoToRepositories: vi.fn(), ...handlers };
  render(<OnboardingWizard entry={entry} {...props} />, { wrapper: withQueryClient() });
  return props;
}

describe('OnboardingWizard', () => {
  afterEach(() => {
    localStorage.clear();
    shared.status = { configured: false };
  });

  it('renders the welcome panel when entry.startStep is omitted', () => {
    renderWizard({ isFirstProject: true });
    expect(screen.getByText('how quodeq works')).toBeInTheDocument();
  });

  it('skip for now sets the skip flag and lands on the repositories tab', () => {
    const { onGoToRepositories } = renderWizard({ isFirstProject: true, source: WIZARD_SOURCE.FIRST_RUN });
    fireEvent.click(screen.getByRole('button', { name: 'skip for now' }));
    expect(localStorage.getItem(SKIP_FLAG)).toBe('true');
    expect(onGoToRepositories).toHaveBeenCalledTimes(1);
  });

  it('opened from Settings: no skip for now, and closing never writes the skip flag', () => {
    const { onClose } = renderWizard({ isFirstProject: false, source: WIZARD_SOURCE.SETTINGS });
    expect(screen.queryByRole('button', { name: 'skip for now' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /close onboarding/i }));
    expect(onClose).toHaveBeenCalled();
    expect(localStorage.getItem(SKIP_FLAG)).toBeNull();
  });

  it('an entry with local projects offers add another', () => {
    renderWizard({ isFirstProject: false, source: WIZARD_SOURCE.ADD });
    expect(screen.getByRole('button', { name: 'add another' })).toBeInTheDocument();
  });

  it('start opens the repository scan until the analyze step exists', () => {
    renderWizard({ isFirstProject: true });
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    expect(screen.getByPlaceholderText(/git@github.com/i)).toBeInTheDocument();
  });

  it('connect opens the evaluations repository step, and back returns to the welcome', () => {
    renderWizard({ isFirstProject: true });
    fireEvent.click(screen.getByRole('button', { name: 'connect' }));
    expect(screen.getByText('evaluations repository')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'back' }));
    expect(screen.getByText('how quodeq works')).toBeInTheDocument();
  });

  it('a connected evaluations repository shows its host and goes to repositories', async () => {
    shared.status = { configured: true, url: 'https://github.com/quodeq/evaluations.git' };
    const { onGoToRepositories } = renderWizard({ isFirstProject: true });
    expect(await screen.findByText('your evaluations repository is connected · github.com/quodeq/evaluations')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'go to repositories' }));
    expect(onGoToRepositories).toHaveBeenCalledTimes(1);
  });

  it('import closes the wizard without the skip flag and runs the entry import action', async () => {
    const onImportProject = vi.fn();
    const { onClose } = renderWizard({ isFirstProject: true, source: WIZARD_SOURCE.FIRST_RUN, onImportProject });
    fireEvent.click(screen.getByRole('button', { name: 'or import an exported archive' }));
    await waitFor(() => expect(onImportProject).toHaveBeenCalledTimes(1));
    expect(onClose).toHaveBeenCalledWith({ saved: false });
    expect(localStorage.getItem(SKIP_FLAG)).toBeNull();
  });

  it('skipping welcome via startStep="repo-scan" mounts the RepoScan step directly', () => {
    renderWizard({ startStep: 'repo-scan', isFirstProject: false });
    expect(screen.getByPlaceholderText(/git@github.com/i)).toBeInTheDocument();
  });

  // useWizardLifecycle decides whether shared content may close the wizard
  // from the step reported here, so the initial step must be reported on mount.
  it('reports its initial step through onStepChange on mount', () => {
    const onStepChange = vi.fn();
    renderWizard({ startStep: STEP_REPO_SCAN, isFirstProject: false }, { onStepChange });
    expect(onStepChange).toHaveBeenCalledWith(STEP_REPO_SCAN);
  });
});
