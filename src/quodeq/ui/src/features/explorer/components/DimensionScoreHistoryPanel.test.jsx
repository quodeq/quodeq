import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DimensionScoreHistoryPanel from './DimensionScoreHistoryPanel.jsx';

const TREND = [
  { runId: 'r3', dateLabel: 'Apr 7', dimensionDetails: [{ dimension: 'maintainability', score: 6.1 }, { dimension: 'reliability', score: 5.9 }] },
  { runId: 'r2', dateLabel: 'Apr 5', dimensionDetails: [{ dimension: 'maintainability', score: 5.7 }] },
  { runId: 'r1', dateLabel: 'Apr 3', dimensionDetails: [{ dimension: 'maintainability', score: 5.2 }] },
];

describe('DimensionScoreHistoryPanel', () => {
  it('renders min/max/avg meta from the dimension series', () => {
    render(<DimensionScoreHistoryPanel trend={TREND} dimension="maintainability" />);
    // min 5.2, max 6.1, avg 5.7
    expect(screen.getByText(/MIN 5.2/)).toBeInTheDocument();
    expect(screen.getByText(/MAX 6.1/)).toBeInTheDocument();
    expect(screen.getByText(/AVG 5.7/)).toBeInTheDocument();
  });

  it('renders an empty-state line when there is no history', () => {
    render(<DimensionScoreHistoryPanel trend={[]} dimension="maintainability" />);
    expect(screen.getByText(/no history yet/i)).toBeInTheDocument();
  });

  it('renders the section label with the bucket size', () => {
    render(<DimensionScoreHistoryPanel trend={TREND} dimension="maintainability" />);
    expect(screen.getByText(/score_history/i)).toBeInTheDocument();
    expect(screen.getByText(/· 3d/)).toBeInTheDocument();
  });
});
