import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { AdvancedAnalysisSettings, TimeLimitSetting } from './ProviderSettings.jsx';
import { PROVIDER_SETTING_KEY } from '../../../constants.js';

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

// The minutes input is named by the row's visible time-limit label.
describe('TimeLimitSetting a11y', () => {
  it.each([
    ['limited', { [PROVIDER_SETTING_KEY.TIME_LIMIT]: '600' }],
    ['unlimited', {}],
  ])('gives the minutes spinbutton the time-limit label as its name when %s', (_mode, state) => {
    render(<TimeLimitSetting state={state} update={vi.fn()} />);
    expect(screen.getByRole('spinbutton')).toHaveAccessibleName('Evaluation time limit');
  });
});
