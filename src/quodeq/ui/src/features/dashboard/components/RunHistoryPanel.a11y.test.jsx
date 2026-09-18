import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RunHistoryPanel from './RunHistoryPanel.jsx';

const TREND = [
  { runId: 'r1', dateISO: '2026-03-25T14:00:00', dateLabel: '25 Mar 2026', numericAverage: 9.5, overallGrade: 'Exemplary' },
  { runId: 'r2', dateISO: '2026-03-24T10:00:00', dateLabel: '24 Mar 2026', numericAverage: 9.0, overallGrade: 'Good' },
  { runId: 'r3', dateISO: '2026-03-23T10:00:00', dateLabel: '23 Mar 2026', numericAverage: 8.5, overallGrade: 'Good' },
];

describe('RunHistoryPanel keyboard access to the run chart', () => {
  it('exposes one "score" button per run and activates onBarClick with the run id', () => {
    const onBarClick = vi.fn();
    render(<RunHistoryPanel trend={TREND} selectedRunId="r1" granularity="day" onBarClick={onBarClick} onGranularityChange={() => {}} />);
    const buttons = screen.getAllByRole('button', { name: /score/ });
    expect(buttons).toHaveLength(TREND.length);
    buttons[0].click();
    expect(onBarClick).toHaveBeenCalledWith('r3'); // chart data is reversed (oldest first)
  });

  it('renders no keyboard controls when onBarClick is not provided', () => {
    render(<RunHistoryPanel trend={TREND} selectedRunId="r1" granularity="day" />);
    expect(screen.queryByRole('button', { name: /score/ })).toBeNull();
  });
});
