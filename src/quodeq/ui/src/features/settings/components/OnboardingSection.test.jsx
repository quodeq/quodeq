import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import OnboardingSection from './OnboardingSection.jsx';
import { SKIPPED_KEY, SKIPPED_VALUE } from '../../onboarding/wizardSteps.js';

afterEach(() => { window.localStorage.removeItem(SKIPPED_KEY); });

describe('OnboardingSection', () => {
  it('renders the block with its row and button', () => {
    render(<OnboardingSection onShowWelcome={() => {}} />);
    expect(screen.getByText('onboarding')).toBeInTheDocument();
    expect(screen.getByText('show the welcome again')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'show welcome' })).toBeInTheDocument();
  });

  it('clears the skipped flag and then opens the welcome', () => {
    window.localStorage.setItem(SKIPPED_KEY, SKIPPED_VALUE);
    const onShowWelcome = vi.fn(() => {
      expect(window.localStorage.getItem(SKIPPED_KEY)).toBeNull();
    });
    render(<OnboardingSection onShowWelcome={onShowWelcome} />);
    fireEvent.click(screen.getByRole('button', { name: 'show welcome' }));
    expect(onShowWelcome).toHaveBeenCalledTimes(1);
    expect(window.localStorage.getItem(SKIPPED_KEY)).toBeNull();
  });
});
