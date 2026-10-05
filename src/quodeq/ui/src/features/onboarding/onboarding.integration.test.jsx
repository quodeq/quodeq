import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// The url clones as a job: the slot reads idle until the post, then done
// with the new project (as the app-level poll would see it).
const clone = vi.hoisted(() => ({ posted: false }));

vi.mock('../../api/index.js', async () => {
  const actual = await vi.importActual('../../api/index.js');
  return {
    ...actual,
    listProjects: vi.fn().mockResolvedValue([]),
    probeGit: vi.fn().mockResolvedValue({ reachable: true }),
    registerProject: vi.fn(async ({ repo }) => {
      clone.posted = true;
      return { started: true, repo, dest: '/u/quodeq/repos/billing' };
    }),
    getCloneStatus: vi.fn(async () => (clone.posted
      ? {
        state: 'done', kind: 'clone', phase: 'done', percent: 100, repo: 'https://github.com/acme/billing.git',
        projectId: 'uuid-9', scanData: { total_files: 7 }, finishedAt: 1700000001000,
      }
      : { state: 'idle', kind: 'clone', phase: null, repo: '', finishedAt: null })),
    listStandards: vi.fn().mockResolvedValue([
      { id: 'std-a', name: 'Security 101', description: 'Common checks' },
      { id: 'std-b', name: 'Code style', description: 'Formatting' },
    ]),
    getProjectInfo: vi.fn().mockResolvedValue({ id: 'uuid-9', runsCount: 0 }),
    getProviderConfigs: vi.fn().mockResolvedValue({}),
    getSharedStatus: vi.fn().mockResolvedValue({ configured: false }),
  };
});

// No provider is detected here: the configured one (seeded below) decides.
vi.mock('./hooks/useProviderDetection.js', () => ({
  useProviderDetection: () => ({ status: 'none', results: [], preselection: null }),
}));

// ProviderTabs is the same component the Settings page uses — heavy and not
// the unit under test here. Stub it; the wizard reads provider+model from
// localStorage anyway, which we seed below.
vi.mock('../settings/components/ProviderTabs.jsx', () => ({
  default: () => <div data-testid="provider-tabs-stub" />,
}));
// The welcome's connected card runs the app's confirmed disconnect, which
// needs the side pane (toasts); this walk never mounts it.
vi.mock('../dashboard/hooks/useSharedDisconnect.js', () => ({ useSharedDisconnect: () => vi.fn() }));

import OnboardingWizard from './components/OnboardingWizard.jsx';
import { withQueryClient } from '../../test-utils/withQueryClient.jsx';

describe('Onboarding integration — happy path', () => {
  beforeEach(() => {
    localStorage.clear();
    clone.posted = false;
    // Seed an active provider so the Provider step's Continue is enabled
    // when the user reaches it (otherwise the wizard can't advance).
    localStorage.setItem('cc-active-provider', 'codex');
    localStorage.setItem('cc-codex-model', 'gpt-5.2-codex');
    // The wizard filters standards by the user's visible-standards setting
    // (matches the Standards tab). Seed both mock ids so the picker shows them.
    localStorage.setItem('quodeq-visible-standards', JSON.stringify(['std-a', 'std-b']));
  });

  it('walks Welcome → Analyze, clones the url and emits onLaunch with the project, the configured provider and the default standard', async () => {
    const onLaunch = vi.fn();
    const onClose = vi.fn();
    render(<OnboardingWizard entry={{ isFirstProject: true }} onLaunch={onLaunch} onClose={onClose} />, { wrapper: withQueryClient() });

    // Welcome
    expect(screen.getByText('how quodeq works')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'start' }));

    // Analyze: a configured provider collapses the reviewer and the standard
    // (every visible standard, read as the default) into one line.
    expect(await screen.findByText('reviewed by Codex CLI · against quodeq default standard')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: 'repository' }), { target: { value: 'https://github.com/acme/billing.git' } });
    fireEvent.click(screen.getByRole('button', { name: 'scan and run' }));

    // The clone lands as a project, and only then does the evaluation start.
    await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
    expect(onLaunch.mock.calls[0][0].projectId).toBe('uuid-9');
    expect(onLaunch.mock.calls[0][0].standardIds).toEqual(['std-a', 'std-b']);
    expect(onLaunch.mock.calls[0][0].repo).toBe('https://github.com/acme/billing.git');
    expect(onLaunch.mock.calls[0][0].provider.id).toBe('codex');
    expect(onLaunch.mock.calls[0][0].provider.model).toBe('gpt-5.2-codex');
  });
});

describe('Onboarding integration — no provider configured', () => {
  beforeEach(() => localStorage.clear());

  it('Continue is disabled until a provider/model is set in localStorage', async () => {
    const onLaunch = vi.fn();
    render(<OnboardingWizard
      entry={{ startStep: 'provider', isFirstProject: false }}
      onLaunch={onLaunch}
      onClose={() => {}}
    />);

    expect(await screen.findByTestId('provider-tabs-stub')).toBeInTheDocument();
    expect(screen.getByText(/pick a provider tab below/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled();
  });
});
