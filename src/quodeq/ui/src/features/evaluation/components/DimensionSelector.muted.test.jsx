import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DimensionSelector, { DIMENSION_SELECTOR_VARIANT_TERMINAL } from './DimensionSelector.jsx';

// Cards with nothing to analyze step back so the ones with work stand out;
// a selected one keeps its check.
const DIMS = [
  { id: 'security', label: 'Security', standardType: 'iso' },
  { id: 'accessibility', label: 'Accessibility', standardType: 'wcag' },
];

describe('DimensionSelector up-to-date cards', () => {
  it('an up-to-date card is muted, selected or not; a card with work is not', () => {
    render(
      <DimensionSelector
        variant={DIMENSION_SELECTOR_VARIANT_TERMINAL}
        allDimensions={DIMS}
        selectedDims={new Set(['security'])}
        onToggle={() => {}}
        onSelectAll={() => {}}
        onClearAll={() => {}}
        dimMetas={{ security: ['up to date'], accessibility: ['3,892 files to analyze'] }}
        upToDateIds={new Set(['security'])}
      />,
    );
    expect(screen.getByRole('button', { name: /security/i })).toHaveClass('eval-dim-card--uptodate');
    expect(screen.getByRole('button', { name: /security/i })).toHaveClass('eval-dim-card--selected');
    expect(screen.getByRole('button', { name: /accessibility/i })).not.toHaveClass('eval-dim-card--uptodate');
  });

  it('says when the selection is the last run\'s', () => {
    render(
      <DimensionSelector
        variant={DIMENSION_SELECTOR_VARIANT_TERMINAL}
        allDimensions={DIMS}
        selectedDims={new Set(['security'])}
        onToggle={() => {}}
        onSelectAll={() => {}}
        onClearAll={() => {}}
        seededFromLastRun
      />,
    );
    expect(document.querySelector('.eval-dims-counter')).toHaveTextContent('1 of 2 selected · as your last run');
  });
});
