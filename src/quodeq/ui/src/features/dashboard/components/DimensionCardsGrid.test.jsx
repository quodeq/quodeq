import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DimensionCardsGrid from './DimensionCardsGrid.jsx';

const DIMS = [
  { dimension: 'maintainability', overallScore: '8.0', previousScore: '2.0', overallGrade: 'B', totals: { violationCount: 1, complianceCount: 4, severity: {} } },
];

describe('DimensionCardsGrid', () => {
  it('uses the period-aware delta from dimTrends on the card badge', () => {
    // run-based fallback would render +6.0 (8.0 - 2.0); the period delta is -0.5
    const dimTrends = { maintainability: { delta: -0.5, scores: [8.5, 8.0] } };
    render(<DimensionCardsGrid sortedDimensions={DIMS} dimTrends={dimTrends} />);
    expect(screen.getByText('-0.5')).toBeInTheDocument();
    expect(screen.queryByText('+6.0')).not.toBeInTheDocument();
  });

  it('falls back to overallScore - previousScore when dimTrends is absent', () => {
    render(<DimensionCardsGrid sortedDimensions={DIMS} />);
    expect(screen.getByText('+6.0')).toBeInTheDocument();
  });
});
