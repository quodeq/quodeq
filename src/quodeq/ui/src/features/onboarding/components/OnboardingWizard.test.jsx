import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import OnboardingWizard from './OnboardingWizard.jsx';

vi.mock('../hooks/useProviderDetection.js', () => ({
  useProviderDetection: () => ({ status: 'detected', preselection: { id: 'codex-cli', classification: 'cli', model: 'gpt-5.2-codex' } }),
}));

vi.mock('../../../api/index.js', () => ({
  registerProject: vi.fn().mockResolvedValue({ projectId: 'uuid-9', scanData: { total_files: 7, languages: { py: 7 }, branches: ['main'], modules: [] } }),
  listStandards: vi.fn().mockResolvedValue([{ id: 'std-a', name: 'Security 101', description: 'Common checks' }]),
  getProjectInfo: vi.fn().mockResolvedValue({ id: 'uuid-9', runsCount: 0 }),
}));

describe('OnboardingWizard', () => {
  it('renders Welcome when entry.startStep is omitted', () => {
    render(<OnboardingWizard entry={{ isFirstProject: true }} onClose={() => {}} onLaunch={() => {}} />);
    expect(screen.getByRole('heading', { name: /welcome to quodeq/i })).toBeInTheDocument();
  });

  it('Maybe later sets the skip flag and calls onClose', () => {
    const onClose = vi.fn();
    render(<OnboardingWizard entry={{ isFirstProject: true }} onClose={onClose} onLaunch={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /maybe later/i }));
    expect(localStorage.getItem('quodeq_onboarding_skipped')).toBe('true');
    expect(onClose).toHaveBeenCalled();
  });

  it('skipping welcome via startStep="repo-scan" mounts the RepoScan step directly', () => {
    render(<OnboardingWizard entry={{ startStep: 'repo-scan', isFirstProject: false }} onClose={() => {}} onLaunch={() => {}} />);
    expect(screen.getByPlaceholderText(/git@github.com/i)).toBeInTheDocument();
  });
});
