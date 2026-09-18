import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import ModelSection from './ModelSection.jsx';

const stubModels = {
  aiModel: '',
  onAiModelChange: () => {},
  fast: '',
  onFastChange: () => {},
  balanced: '',
  onBalancedChange: () => {},
  thorough: '',
  onThoroughChange: () => {},
};

const CLIENTS = [
  { id: 'claude', label: 'Claude', type: 'cli' },
  { id: 'ollama', label: 'Ollama', type: 'cli' },
];

// #6398 - the client pill group is a mutually-exclusive choice marked only
// by a CSS class; it needs radiogroup/radio semantics.
describe('ModelSection client pill group a11y', () => {
  it('exposes the client pills as a labelled radiogroup', () => {
    render(
      <ModelSection
        aiCmd={{ value: 'claude', onApply: vi.fn() }}
        models={stubModels}
        availableClients={CLIENTS}
      />,
    );
    expect(screen.getByRole('radiogroup', { name: 'Assistant client' })).toBeInTheDocument();
  });

  it('marks only the selected client as the checked radio', () => {
    render(
      <ModelSection
        aiCmd={{ value: 'ollama', onApply: vi.fn() }}
        models={stubModels}
        availableClients={CLIENTS}
      />,
    );
    expect(screen.getByRole('radio', { name: 'Ollama' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'Claude' })).toHaveAttribute('aria-checked', 'false');
  });
});
