import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

vi.mock('../../api/index.js', async () => {
  const actual = await vi.importActual('../../api/index.js');
  return {
    ...actual,
    listProjects: vi.fn().mockResolvedValue([]),
    registerProject: vi.fn().mockResolvedValue({
      projectId: 'uuid-9',
      scanData: { total_files: 7, languages: { py: 7 }, branches: ['main'], modules: [] },
    }),
    listStandards: vi.fn().mockResolvedValue([
      { id: 'std-a', name: 'Security 101', description: 'Common checks' },
      { id: 'std-b', name: 'Code style', description: 'Formatting' },
    ]),
    getProjectInfo: vi.fn().mockResolvedValue({ id: 'uuid-9', runsCount: 0 }),
    getProviderConfigs: vi.fn().mockResolvedValue({}),
  };
});

// ScanProgress depends on <EvalLogProvider> which is not in the wizard tree —
// for this integration test we render a simple stub instead.
vi.mock('../evaluation/components/ScanProgress.jsx', () => ({
  default: () => <div data-testid="scan-progress-stub" />,
}));

// ProviderTabs is the same component the Settings page uses — heavy and not
// the unit under test here. Stub it; the wizard reads provider+model from
// localStorage anyway, which we seed below.
vi.mock('../settings/components/ProviderTabs.jsx', () => ({
  default: () => <div data-testid="provider-tabs-stub" />,
}));

import OnboardingWizard from './components/OnboardingWizard.jsx';

describe('Onboarding integration — happy path', () => {
  beforeEach(() => {
    localStorage.clear();
    // Seed an active provider so the Provider step's Continue is enabled
    // when the user reaches it (otherwise the wizard can't advance).
    localStorage.setItem('cc-active-provider', 'codex');
    localStorage.setItem('cc-codex-model', 'gpt-5.2-codex');
    // The wizard filters standards by the user's visible-standards setting
    // (matches the Standards tab). Seed both mock ids so the picker shows them.
    localStorage.setItem('quodeq-visible-standards', JSON.stringify(['std-a', 'std-b']));
  });

  it('walks Welcome → Repo & Scan → Provider → Standard & Launch and emits onLaunch', async () => {
    const onLaunch = vi.fn();
    const onClose = vi.fn();
    render(<OnboardingWizard entry={{ isFirstProject: true }} onLaunch={onLaunch} onClose={onClose} />);

    // Welcome
    expect(screen.getByRole('heading', { name: /welcome to quodeq/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /get started/i }));

    // Repo & Scan — placeholder is the most stable on-screen identifier
    // for "we're on the repo step" after the terminal redesign.
    fireEvent.change(screen.getByPlaceholderText(/git@github.com/i), { target: { value: '/local/path' } });
    fireEvent.click(screen.getByRole('button', { name: /scan repository/i }));
    // Scanned-state stat tile — total_files=7 from the mock. Use getAllByText
    // because '7' also appears as a language count in the pill row.
    await waitFor(() => expect(screen.getAllByText('7').length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole('button', { name: /^continue$/i })[0]);

    // Provider — embedded ProviderTabs (stubbed); the active provider/model
    // comes from localStorage and the summary line shows it.
    expect(await screen.findByTestId('provider-tabs-stub')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: /^continue$/i }));

    // Standard & Launch — pitch text is unchanged and uniquely identifies this step
    expect(screen.getByText(/pick one for your first run/i)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/security 101/i));
    fireEvent.click(screen.getByRole('button', { name: /start evaluation/i }));

    await waitFor(() => expect(onLaunch).toHaveBeenCalled());
    expect(onLaunch.mock.calls[0][0].standardIds).toEqual(['std-a']);
    expect(onLaunch.mock.calls[0][0].projectId).toBe('uuid-9');
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
