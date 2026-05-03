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
  };
});

vi.mock('./hooks/useProviderDetection.js', () => ({
  useProviderDetection: () => ({
    status: 'detected',
    preselection: { id: 'codex-cli', classification: 'cli', model: 'gpt-5.2-codex' },
  }),
}));

// ScanProgress depends on <EvalLogProvider> which is not in the wizard tree —
// for this integration test we render a simple stub instead.
vi.mock('../evaluation/components/ScanProgress.jsx', () => ({
  default: () => <div data-testid="scan-progress-stub" />,
}));

import OnboardingWizard from './components/OnboardingWizard.jsx';

describe('Onboarding integration — happy path', () => {
  beforeEach(() => localStorage.clear());

  it('walks Welcome → Repo & Scan → Provider → Standard & Launch and emits onLaunch', async () => {
    const onLaunch = vi.fn();
    const onClose = vi.fn();
    render(<OnboardingWizard entry={{ isFirstProject: true }} onLaunch={onLaunch} onClose={onClose} />);

    // Welcome
    expect(screen.getByRole('heading', { name: /welcome to quodeq/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /get started/i }));

    // Repo & Scan
    expect(screen.getByRole('heading', { name: /add a repository/i })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/git@github.com/i), { target: { value: '/local/path' } });
    fireEvent.click(screen.getByRole('button', { name: /scan repository/i }));
    await waitFor(() => expect(screen.getByText(/we found:/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /continue → set up evaluation/i }));

    // Provider — pre-recommended view should be visible
    expect(await screen.findByText(/codex cli/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^continue$/i }));

    // Standard & Launch
    expect(screen.getByRole('heading', { name: /pick a standard/i })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/security 101/i));
    fireEvent.click(screen.getByRole('button', { name: /start evaluation/i }));

    await waitFor(() => expect(onLaunch).toHaveBeenCalled());
    expect(onLaunch.mock.calls[0][0].standardIds).toEqual(['std-a']);
    expect(onLaunch.mock.calls[0][0].projectId).toBe('uuid-9');
    expect(onLaunch.mock.calls[0][0].provider.id).toBe('codex-cli');
  });
});

describe('Onboarding integration — no provider detected', () => {
  beforeEach(() => localStorage.clear());

  it('opens Provider step in comparison view and lets user pick Cloud', async () => {
    vi.resetModules();
    vi.doMock('./hooks/useProviderDetection.js', () => ({
      useProviderDetection: () => ({ status: 'none', preselection: null }),
    }));
    const { default: OnboardingWizardLocal } = await import('./components/OnboardingWizard.jsx');

    const onLaunch = vi.fn();
    render(<OnboardingWizardLocal
      entry={{ startStep: 'provider', isFirstProject: false }}
      onLaunch={onLaunch}
      onClose={() => {}}
    />);

    // Comparison view should be visible (the three card headings render).
    expect(await screen.findByRole('heading', { name: /local cli/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /cloud api/i })).toBeInTheDocument();

    // Continue is disabled because no model is selected.
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled();
  });
});
