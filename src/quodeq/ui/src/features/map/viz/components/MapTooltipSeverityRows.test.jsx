import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import MapTooltipSeverityRows from './MapTooltipSeverityRows.jsx';

const rows = (container) => [...container.querySelectorAll('.map-tooltip-row')]
  .map((r) => [r.textContent, r.style.color]);

describe('MapTooltipSeverityRows', () => {
  it('shows a coloured row for each severity with a count above zero', () => {
    const { container } = render(<MapTooltipSeverityRows severity={{ critical: 2, major: 0, minor: 1 }} />);
    expect(rows(container)).toEqual([
      ['Critical2', 'var(--color-sev-critical-text)'],
      ['Minor1', 'var(--color-sev-minor-text)'],
    ]);
  });

  it('shows nothing without a severity tally', () => {
    const { container } = render(<MapTooltipSeverityRows severity={undefined} />);
    expect(container.innerHTML).toBe('');
  });
});
