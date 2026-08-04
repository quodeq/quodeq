import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RunHistoryPanel, { RunHistoryTooltip } from './RunHistoryPanel.jsx';

const TREND = [
  { runId: 'r1', dateISO: '2026-03-25T14:00:00', dateLabel: '25 Mar 2026', numericAverage: 9.5, overallGrade: 'Exemplary' },
  { runId: 'r2', dateISO: '2026-03-24T10:00:00', dateLabel: '24 Mar 2026', numericAverage: 9.0, overallGrade: 'Good' },
  { runId: 'r3', dateISO: '2026-03-23T10:00:00', dateLabel: '23 Mar 2026', numericAverage: 8.5, overallGrade: 'Good' },
];

describe('RunHistoryPanel', () => {
  it('renders the granularity selector reflecting the current value', () => {
    render(<RunHistoryPanel trend={TREND} selectedRunId="r1" granularity="week" onGranularityChange={() => {}} />);
    expect(screen.getByLabelText('Group score history by')).toHaveValue('week');
  });

  it('shows a granularity-aware label suffix (w for week)', () => {
    render(<RunHistoryPanel trend={TREND} selectedRunId="r1" granularity="week" onGranularityChange={() => {}} />);
    expect(screen.getByText(/score_history · 3w/i)).toBeInTheDocument();
  });

  it('calls onGranularityChange when the selector changes', () => {
    const onGranularityChange = vi.fn();
    render(<RunHistoryPanel trend={TREND} selectedRunId="r1" granularity="day" onGranularityChange={onGranularityChange} />);
    fireEvent.change(screen.getByLabelText('Group score history by'), { target: { value: 'month' } });
    expect(onGranularityChange).toHaveBeenCalledWith('month');
  });

  it('keeps the selector but hides MIN/MAX/AVG when collapsed to a single bucket', () => {
    render(<RunHistoryPanel trend={[TREND[0]]} selectedRunId="r1" granularity="month" onGranularityChange={() => {}} />);
    expect(screen.getByLabelText('Group score history by')).toBeInTheDocument();
    expect(screen.queryByText(/MIN /)).not.toBeInTheDocument();
  });

  // Every point on this chart is the PROJECT grade (latest known score per
  // dimension), not the grade of that one scan. So a scan that only measured
  // clean-architecture still plots a full project number. Without saying how
  // much the scan refreshed, a point backed by 1 of 7 dimensions is
  // indistinguishable from one backed by a full sweep.
  it('says how much of the project a partial scan refreshed', () => {
    const entry = {
      periodLabel: '1 Aug 2026', numericAverage: 7.6, overallGrade: 'Good',
      dimensionsCount: 1, accumulatedDimensionsCount: 7,
    };
    render(<RunHistoryTooltip active payload={[{ payload: entry }]} />);
    expect(screen.getByText(/1.*7/)).toBeInTheDocument();
  });

  it('does not annotate a scan that refreshed every dimension', () => {
    const entry = {
      periodLabel: '3 Aug 2026', numericAverage: 6.9, overallGrade: 'Adequate',
      dimensionsCount: 7, accumulatedDimensionsCount: 7,
    };
    const { container } = render(<RunHistoryTooltip active payload={[{ payload: entry }]} />);
    expect(container.querySelector('.rht-coverage')).toBeNull();
  });

  it('hides the stats line instead of rendering Infinity when no bucket has a numeric score', () => {
    const nanTrend = [
      { runId: 'r1', dateISO: '2026-03-25T14:00:00', dateLabel: '25 Mar 2026', numericAverage: 'n/a', overallGrade: 'Good' },
      { runId: 'r2', dateISO: '2026-03-24T10:00:00', dateLabel: '24 Mar 2026', numericAverage: 'n/a', overallGrade: 'Good' },
    ];
    render(<RunHistoryPanel trend={nanTrend} selectedRunId="r1" granularity="day" onGranularityChange={() => {}} />);
    expect(screen.queryByText(/MIN /)).not.toBeInTheDocument();
    expect(screen.queryByText(/Infinity/)).not.toBeInTheDocument();
  });
});
