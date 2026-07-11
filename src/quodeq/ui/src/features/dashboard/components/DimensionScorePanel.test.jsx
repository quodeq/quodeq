import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DimensionScorePanel from './DimensionScorePanel.jsx';

const DIMS = [
  { dimension: 'maintainability', overallScore: '8.0', previousScore: '2.0', totalViolations: 3 },
];

describe('DimensionScorePanel', () => {
  it('shows the period-aware delta from dimTrends, not overallScore - previousScore', () => {
    // run-based fallback would render +6.0 (8.0 - 2.0); the period delta is -0.5
    const dimTrends = { maintainability: { delta: -0.5, scores: [8.5, 8.0] } };
    render(<DimensionScorePanel dimensions={DIMS} dimTrends={dimTrends} />);
    expect(screen.getByText('-0.5')).toBeInTheDocument();
    expect(screen.queryByText('+6.0')).not.toBeInTheDocument();
  });

  it('falls back to overallScore - previousScore when dimTrends is absent', () => {
    render(<DimensionScorePanel dimensions={DIMS} />);
    expect(screen.getByText('+6.0')).toBeInTheDocument();
  });

  it('renders one sparkline bar per period score', () => {
    const dimTrends = { maintainability: { delta: 0.5, scores: [7.0, 7.5, 8.0] } };
    const { container } = render(<DimensionScorePanel dimensions={DIMS} dimTrends={dimTrends} />);
    expect(container.querySelectorAll('.dim-sparkline rect')).toHaveLength(3);
  });

  it('renders no trend badge when the period delta is null (single bucket)', () => {
    const dimTrends = { maintainability: { delta: null, scores: [8.0] } };
    const { container } = render(<DimensionScorePanel dimensions={DIMS} dimTrends={dimTrends} />);
    expect(container.querySelector('.trend-badge')).toBeNull();
  });
});
