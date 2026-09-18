import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DimensionGaugeCard from './DimensionGaugeCard.jsx';

const baseItem = {
  dimension: 'modifiability',
  overallScore: '7.5/10',
  totals: { violationCount: 4, complianceCount: 20, severity: { critical: 0, major: 1, minor: 3 } },
};

describe('DimensionGaugeCard accessible score summary', () => {
  it('exposes the score and grade to assistive tech even though the gauge SVG is aria-hidden', () => {
    render(<DimensionGaugeCard item={baseItem} onDimensionClick={() => {}} />);
    // The gauge itself stays aria-hidden (decorative SVG); the sr-only
    // sibling carries the same information as real accessible text.
    expect(screen.getByText(/score 7\.5, grade good/i)).toBeInTheDocument();
  });
});
