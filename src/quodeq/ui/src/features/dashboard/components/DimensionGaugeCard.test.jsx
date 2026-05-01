import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DimensionGaugeCard from './DimensionGaugeCard.jsx';

const baseItem = {
  dimension: 'modifiability',
  overallScore: '4.7',
  totals: { violationCount: 116, complianceCount: 232, severity: { critical: 0, major: 11, minor: 105 } },
};

describe('DimensionGaugeCard', () => {
  it('renders a normal gauge with score and grade', () => {
    render(<DimensionGaugeCard item={baseItem} onDimensionClick={() => {}} />);
    expect(screen.getByText('4.7')).toBeInTheDocument();
    expect(screen.getByText(/VIOL/)).toBeInTheDocument();
  });

  it('renders an insufficient state when isInsufficient=true', () => {
    render(
      <DimensionGaugeCard
        item={{ dimension: 'analyzability', overallScore: null }}
        isInsufficient
        onDimensionClick={() => {}}
      />,
    );
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText(/INSUFFICIENT/i)).toBeInTheDocument();
    // No VIOL meta line in insufficient state
    expect(screen.queryByText(/VIOL/)).toBeNull();
  });
});
