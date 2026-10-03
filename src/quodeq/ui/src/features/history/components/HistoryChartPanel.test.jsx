import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HistoryChartPanel, { HistoryRunTooltip } from './HistoryChartPanel.jsx';

const trend = [
  { runId: 'r2', dateISO: '2026-09-02', dateLabel: '2 Sep', runNumericAverage: '8.5', overallGrade: 'Good', dimensionDetails: [{ critical: 1, majors: 3, openTypes: 33 }] },
  { runId: 'r1', dateISO: '2026-09-01', dateLabel: '1 Sep', runNumericAverage: '8.0', overallGrade: 'Good', dimensionDetails: [{ critical: 0, majors: 5, openTypes: 40 }] },
];

describe('HistoryChartPanel', () => {
  it('draws no legend and no count lines: the score chart stays as it was', () => {
    const { container } = render(<HistoryChartPanel trend={trend} selectedRunId="r2" onBarClick={() => {}} />);
    expect(screen.queryByText(/score · majors/)).not.toBeInTheDocument();
    expect(container.querySelector('.chart-legend')).toBeNull();
  });

  it("the tooltip names the run's criticals, then its majors without them, like the strip", () => {
    render(<HistoryRunTooltip active payload={[{ payload: { dateLabel: '2 Sep', numericAverage: 8.5, overallGrade: 'Good', critical: 1, majors: 3, openTypes: 33 } }]} />);
    expect(screen.getByText('1 critical · 2 majors · 33 open types')).toBeInTheDocument();
  });

  it('countsLine without a critical count names majors and open types only', () => {
    render(<HistoryRunTooltip active payload={[{ payload: { dateLabel: '2 Sep', numericAverage: 8.5, overallGrade: 'Good', majors: 3, openTypes: 33 } }]} />);
    expect(screen.getByText('3 majors · 33 open types')).toBeInTheDocument();
  });

  it('a point without counts gets no counts line', () => {
    const { container } = render(<HistoryRunTooltip active payload={[{ payload: { dateLabel: '2 Sep', numericAverage: 8.5, overallGrade: 'Good' } }]} />);
    expect(container.querySelector('.rht-counts')).toBeNull();
    expect(container.textContent).not.toMatch(/undefined|NaN/);
  });
});
