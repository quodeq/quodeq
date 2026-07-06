import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DimensionScoreHistoryPanel from './DimensionScoreHistoryPanel.jsx';

const TREND = [
  { runId: 'r2', dateISO: '2026-04-05T10:00:00', dateLabel: 'Apr 5', dimensionDetails: [{ dimension: 'maintainability', score: 5.7 }] },
  { runId: 'r1', dateISO: '2026-04-03T10:00:00', dateLabel: 'Apr 3', dimensionDetails: [{ dimension: 'maintainability', score: 5.2 }] },
];

// #1800: the old keyboard handler only ever activated the LAST data point, so
// keyboard users could not select earlier runs. The chart now exposes one
// focusable control per run that reaches the same handler as a mouse click.
describe('DimensionScoreHistoryPanel chart keyboard accessibility (#1800)', () => {
  it('exposes a focusable control for every run, not just the last', () => {
    render(
      <DimensionScoreHistoryPanel trend={TREND} dimension="maintainability" onBarClick={vi.fn()} />,
    );
    expect(screen.getAllByRole('button')).toHaveLength(2);
  });

  it('activating an EARLIER run fires onBarClick with that run (the #1800 gap)', () => {
    const onBarClick = vi.fn();
    render(
      <DimensionScoreHistoryPanel trend={TREND} dimension="maintainability" onBarClick={onBarClick} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Apr 3/ }));
    expect(onBarClick).toHaveBeenCalledTimes(1);
    expect(onBarClick.mock.calls[0][0]).toMatchObject({ runId: 'r1' });
  });

  it('activates on Enter and Space', () => {
    const onBarClick = vi.fn();
    render(
      <DimensionScoreHistoryPanel trend={TREND} dimension="maintainability" onBarClick={onBarClick} />,
    );
    const btn = screen.getByRole('button', { name: /Apr 5/ });
    fireEvent.keyDown(btn, { key: 'Enter' });
    fireEvent.keyDown(btn, { key: ' ' });
    expect(onBarClick).toHaveBeenCalledTimes(2);
    expect(onBarClick.mock.calls[0][0]).toMatchObject({ runId: 'r2' });
  });

  it('renders no keyboard controls when onBarClick is absent', () => {
    render(<DimensionScoreHistoryPanel trend={TREND} dimension="maintainability" />);
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });
});
