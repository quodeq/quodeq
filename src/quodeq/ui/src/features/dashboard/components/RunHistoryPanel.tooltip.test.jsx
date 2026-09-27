import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { RunHistoryTooltip } from './RunHistoryPanel.jsx';

describe('RunHistoryTooltip counts line', () => {
  it('names the run the counts belong to, since the score is the project grade', () => {
    render(<RunHistoryTooltip active payload={[{ payload: { dateLabel: '2 Sep', periodLabel: 'Week 36', numericAverage: 8.5, overallGrade: 'Good', majors: 2, openTypes: 3, dimensionsCount: 7, accumulatedDimensionsCount: 7 } }]} />);
    expect(screen.getByText('latest run 2 Sep: 2 majors · 3 open types')).toBeInTheDocument();
  });
});
