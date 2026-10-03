import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useOnboardingWizardHandlers } from './useOnboardingWizardHandlers.js';

const SKIP_FLAG = 'quodeq_onboarding_skipped';

function setup(extra = {}) {
  const opts = {
    wizard: { state: {}, goToStep: vi.fn() },
    onClose: vi.fn(), onLaunch: vi.fn(), onGoToRepositories: vi.fn(), ...extra,
  };
  const { result } = renderHook(() => useOnboardingWizardHandlers(opts));
  return { result, opts };
}

describe('useOnboardingWizardHandlers resume walk', () => {
  it('continue goes from the provider step to the standard step, back returns', () => {
    const { result, opts } = setup({ wizard: { state: { step: 'provider' }, goToStep: vi.fn() } });
    result.current.nextStep();
    expect(opts.wizard.goToStep).toHaveBeenCalledWith('standard-launch');
  });

  it('back from the standard step returns to the provider step', () => {
    const { result, opts } = setup({ wizard: { state: { step: 'standard-launch' }, goToStep: vi.fn() } });
    result.current.prevStep();
    expect(opts.wizard.goToStep).toHaveBeenCalledWith('provider');
  });
});

describe('useOnboardingWizardHandlers handleSkipWelcome', () => {
  afterEach(() => localStorage.clear());

  it('writes the skip flag and goes to repositories', () => {
    const { result, opts } = setup();
    result.current.handleSkipWelcome();
    expect(localStorage.getItem(SKIP_FLAG)).toBe('true');
    expect(opts.onGoToRepositories).toHaveBeenCalledTimes(1);
  });

  it('from Settings never writes the skip flag', () => {
    const { result } = setup({ fromSettings: true });
    result.current.handleSkipWelcome();
    expect(localStorage.getItem(SKIP_FLAG)).toBeNull();
  });
});

describe('useOnboardingWizardHandlers handleLaunch', () => {
  const state = {
    projectId: 'from-state', repo: { value: 'https://github.com/acme/billing.git', scopePath: null, branch: null },
    provider: { id: 'claude', model: 'claude-sonnet-5-5' }, totalTimeLimitS: 600,
  };

  it('launches the project the analyze screen registered, with the lifecycle payload unchanged', () => {
    const { result, opts } = setup({ wizard: { state, startLaunch: vi.fn() } });
    result.current.handleLaunch({ projectId: 'p1', standardIds: ['default'] });
    expect(opts.wizard.startLaunch).toHaveBeenCalledTimes(1);
    expect(opts.onLaunch).toHaveBeenCalledWith({
      projectId: 'p1', repo: 'https://github.com/acme/billing.git', scopePath: null, branch: null,
      provider: { id: 'claude', model: 'claude-sonnet-5-5' }, standardIds: ['default'], totalTimeLimitS: 600,
    });
  });

  it('without a project id (the resume walk) it launches the one in state', () => {
    const { result, opts } = setup({ wizard: { state, startLaunch: vi.fn() } });
    result.current.handleLaunch({ standardIds: ['default'] });
    expect(opts.onLaunch.mock.calls[0][0]).toMatchObject({ projectId: 'from-state', standardIds: ['default'] });
  });
});
