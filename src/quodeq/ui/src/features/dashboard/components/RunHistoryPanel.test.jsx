import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RunHistoryPanel from './RunHistoryPanel.jsx';

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
