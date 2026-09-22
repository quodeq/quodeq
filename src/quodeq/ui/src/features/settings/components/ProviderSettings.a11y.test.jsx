import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { AdvancedAnalysisSettings } from './ProviderSettings.jsx';

// #6394 / #6395 - the per-dimension/grouped and verify on/off pill pairs are
// mutually-exclusive choices marked only by a CSS class; they need
// radiogroup/radio semantics.
describe('AdvancedAnalysisSettings toggle a11y', () => {
  const setup = (state = {}) => render(
    <AdvancedAnalysisSettings state={state} update={vi.fn()} />,
  );

  it('exposes the analysis-mode pair as a labelled radiogroup', () => {
    setup();
    expect(screen.getByRole('radiogroup', { name: 'Violation grouping' })).toBeInTheDocument();
  });

  it('marks the per-dimension option checked when per-dimension is not false', () => {
    setup({ 'per-dimension': 'true' });
    const group = screen.getByRole('radiogroup', { name: 'Violation grouping' });
    expect(screen.getByRole('radio', { name: 'Per-dimension' })).toHaveAttribute('aria-checked', 'true');
    expect(group).toBeInTheDocument();
  });

  it('exposes the verify-findings pair as a labelled radiogroup', () => {
    setup();
    expect(screen.getByRole('radiogroup', { name: 'Verify findings' })).toBeInTheDocument();
  });

  it('marks the Off option checked when verify is explicitly false', () => {
    setup({ verify: 'false' });
    expect(screen.getByRole('radio', { name: 'Off' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: 'On' })).toHaveAttribute('aria-checked', 'false');
  });
});
