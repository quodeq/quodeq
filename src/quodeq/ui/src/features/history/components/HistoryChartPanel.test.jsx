import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HistoryChartPanel, { HistoryRunTooltip } from './HistoryChartPanel.jsx';

const trend = [
  { runId: 'r2', dateISO: '2026-09-02', dateLabel: '2 Sep', runNumericAverage: '8.5', overallGrade: 'Good', dimensionDetails: [{ majors: 3, openTypes: 33 }] },
  { runId: 'r1', dateISO: '2026-09-01', dateLabel: '1 Sep', runNumericAverage: '8.0', overallGrade: 'Good', dimensionDetails: [{ majors: 5, openTypes: 40 }] },
];

describe('HistoryChartPanel', () => {
  it('shows the series legend', () => {
    render(<HistoryChartPanel trend={trend} selectedRunId="r2" onBarClick={() => {}} />);
    expect(screen.getByText('score · majors · open types')).toBeInTheDocument();
  });

  it('the tooltip names the run\'s majors and open types', () => {
    render(<HistoryRunTooltip active payload={[{ payload: { dateLabel: '2 Sep', numericAverage: 8.5, overallGrade: 'Good', majors: 3, openTypes: 33 } }]} />);
    expect(screen.getByText('3 majors · 33 open types')).toBeInTheDocument();
  });
});
