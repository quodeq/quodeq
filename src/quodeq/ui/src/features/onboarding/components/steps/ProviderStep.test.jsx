import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

vi.mock('../../../../api/index.js', () => ({
  getProviderConfigs: vi.fn().mockResolvedValue({}),
}));

// Stub ProviderTabs — we don't want to pull the whole settings tree into a
// unit test. The integration is already covered by the wizard integration
// test that mounts the real component.
vi.mock('../../../settings/components/ProviderTabs.jsx', () => ({
  default: () => <div data-testid="provider-tabs-stub" />,
}));

import ProviderStep from './ProviderStep.jsx';

const noop = () => {};
const baseState = (over = {}) => ({
  provider: { id: null, classification: null, model: null },
  ...over,
});
const baseActions = { setProvider: vi.fn(), setTimeLimit: vi.fn() };

describe('ProviderStep', () => {
  beforeEach(() => {
    localStorage.clear();
    baseActions.setProvider.mockReset();
    baseActions.setTimeLimit.mockReset();
  });

  it('renders the embedded ProviderTabs and the empty-active hint when nothing is selected', () => {
    render(<ProviderStep state={baseState()} actions={baseActions} onContinue={noop} onBack={noop} />);
    expect(screen.getByText(/pick a provider tab below/i)).toBeInTheDocument();
    expect(screen.getByTestId('provider-tabs-stub')).toBeInTheDocument();
  });

  it('Continue is disabled when no active provider is selected', () => {
    render(<ProviderStep state={baseState()} actions={baseActions} onContinue={noop} onBack={noop} />);
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled();
  });

  it('shows the selected provider summary and enables Continue when localStorage has both keys', async () => {
    localStorage.setItem('cc-active-provider', 'codex');
    localStorage.setItem('cc-codex-model', 'gpt-5.2-codex');
    render(<ProviderStep state={baseState()} actions={baseActions} onContinue={noop} onBack={noop} />);
    await waitFor(() => expect(screen.getByText(/codex cli/i)).toBeInTheDocument());
    expect(screen.getByText('gpt-5.2-codex')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^continue$/i })).not.toBeDisabled();
  });

  it('Continue calls setProvider with the localStorage values then onContinue', async () => {
    localStorage.setItem('cc-active-provider', 'claude');
    localStorage.setItem('cc-claude-model', 'sonnet-4.6');
    const onContinue = vi.fn();
    render(<ProviderStep state={baseState()} actions={baseActions} onContinue={onContinue} onBack={noop} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: /^continue$/i }));
    expect(baseActions.setProvider).toHaveBeenCalledWith({
      id: 'claude',
      model: 'sonnet-4.6',
      classification: null,
    });
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it('Continue propagates the per-provider time-limit (Unlimited = 0) into wizard state', async () => {
    localStorage.setItem('cc-active-provider', 'ollama');
    localStorage.setItem('cc-ollama-model', 'gemma4:26b');
    localStorage.setItem('cc-ollama-time-limit', '0');
    render(<ProviderStep state={baseState()} actions={baseActions} onContinue={noop} onBack={noop} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: /^continue$/i }));
    expect(baseActions.setTimeLimit).toHaveBeenCalledWith(0);
  });

  it('Continue does not call setTimeLimit when the per-provider time-limit is unset', async () => {
    localStorage.setItem('cc-active-provider', 'codex');
    localStorage.setItem('cc-codex-model', 'gpt-5.2-codex');
    render(<ProviderStep state={baseState()} actions={baseActions} onContinue={noop} onBack={noop} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /^continue$/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: /^continue$/i }));
    expect(baseActions.setTimeLimit).not.toHaveBeenCalled();
  });
});
