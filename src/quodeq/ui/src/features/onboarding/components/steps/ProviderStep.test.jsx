import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ProviderStep from './ProviderStep.jsx';

const noop = () => {};

const baseState = {
  provider: { id: null, classification: null, model: null },
  providerView: 'pre-recommended',
  totalTimeLimitS: 600,
};
const baseActions = { setProvider: noop, setProviderView: noop, setTimeLimit: noop };

describe('ProviderStep', () => {
  it('shows pre-recommended view with detected provider name and Change link', () => {
    render(<ProviderStep
      state={{ ...baseState, provider: { id: 'codex-cli', classification: 'cli', model: 'gpt-5.2-codex' } }}
      actions={baseActions}
      detection={{ status: 'detected', preselection: { id: 'codex-cli', classification: 'cli', model: 'gpt-5.2-codex' } }}
      onContinue={noop}
      onBack={noop}
    />);
    expect(screen.getByText(/codex cli/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /change provider/i })).toBeInTheDocument();
  });

  it('shows comparison view with three cards when detection finds nothing', () => {
    render(<ProviderStep
      state={{ ...baseState, providerView: 'comparison' }}
      actions={baseActions}
      detection={{ status: 'none', preselection: null }}
      onContinue={noop}
      onBack={noop}
    />);
    expect(screen.getByRole('heading', { name: /local cli/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /local api \(ollama\)/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /cloud api/i })).toBeInTheDocument();
  });

  it('clicking Change provider toggles to comparison view', () => {
    const setProviderView = vi.fn();
    render(<ProviderStep
      state={{ ...baseState, provider: { id: 'codex-cli', classification: 'cli', model: 'gpt-5.2-codex' } }}
      actions={{ ...baseActions, setProviderView }}
      detection={{ status: 'detected', preselection: { id: 'codex-cli', classification: 'cli', model: 'gpt-5.2-codex' } }}
      onContinue={noop}
      onBack={noop}
    />);
    fireEvent.click(screen.getByRole('button', { name: /change provider/i }));
    expect(setProviderView).toHaveBeenCalledWith('comparison');
  });

  it('Continue is disabled when no model is selected', () => {
    render(<ProviderStep
      state={baseState}
      actions={baseActions}
      detection={{ status: 'none', preselection: null }}
      onContinue={noop}
      onBack={noop}
    />);
    expect(screen.getByRole('button', { name: /^continue$/i })).toBeDisabled();
  });

  it('time-limit chip selection calls setTimeLimit', () => {
    const setTimeLimit = vi.fn();
    render(<ProviderStep
      state={{ ...baseState, provider: { id: 'codex-cli', classification: 'cli', model: 'gpt-5.2-codex' } }}
      actions={{ ...baseActions, setTimeLimit }}
      detection={{ status: 'detected', preselection: { id: 'codex-cli', classification: 'cli', model: 'gpt-5.2-codex' } }}
      onContinue={noop}
      onBack={noop}
    />);
    fireEvent.click(screen.getByRole('radio', { name: /^30 min$/i }));
    expect(setTimeLimit).toHaveBeenCalledWith(1800);
  });
});
