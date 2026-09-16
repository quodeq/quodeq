import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DimensionCard from './DimensionCard.jsx';

const DIM = {
  dimension: 'reliability', overallScore: '8.0/10', overallGrade: 'B',
  violations: [], compliance: [], principles: [],
  totals: {
    violationCount: 273, complianceCount: 40,
    severity: { critical: 0, major: 57 }, violationsPer100Files: 12.1,
  },
};

describe('DimensionCard density tile', () => {
  it('shows violations per 100 files next to the grade', () => {
    render(<DimensionCard dimension={DIM} />);
    expect(screen.getByText('Per 100 files')).toBeInTheDocument();
    expect(screen.getByText('12.1')).toBeInTheDocument();
  });

  it('shows a dash when the report has no density', () => {
    const dim = { ...DIM, totals: { ...DIM.totals, violationsPer100Files: null } };
    render(<DimensionCard dimension={dim} />);
    expect(screen.getByText('Per 100 files').nextElementSibling).toHaveTextContent('-');
  });
});
