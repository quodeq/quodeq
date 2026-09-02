import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DimensionScoreHistoryPanel from './DimensionScoreHistoryPanel.jsx';

const TREND = [
  { runId: 'r3', dateISO: '2026-04-07T10:00:00', dateLabel: 'Apr 7', dimensionDetails: [{ dimension: 'maintainability', score: 6.1 }, { dimension: 'reliability', score: 5.9 }] },
  { runId: 'r2', dateISO: '2026-04-05T10:00:00', dateLabel: 'Apr 5', dimensionDetails: [{ dimension: 'maintainability', score: 5.7 }] },
  { runId: 'r1', dateISO: '2026-04-03T10:00:00', dateLabel: 'Apr 3', dimensionDetails: [{ dimension: 'maintainability', score: 5.2 }] },
];

// recharts' <Bar> only recognizes per-bar <Cell> colors when they are its
// *direct* JSX children; ResponsiveContainer needs a ResizeObserver and a
// non-zero container size to actually lay the bars out under jsdom.
function stubChartLayout() {
  global.ResizeObserver = class {
    constructor(cb) { this.cb = cb; }
    observe(el) { this.cb([{ target: el, contentRect: { width: 400, height: 160 } }]); }
    unobserve() {}
    disconnect() {}
  };
  Element.prototype.getBoundingClientRect = function () {
    return { width: 400, height: 160, top: 0, left: 0, bottom: 160, right: 400, x: 0, y: 0, toJSON() {} };
  };
}

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

  it('collapses runs into ISO-week buckets when granularity is week', () => {
    // Apr 3 and Apr 5 are the same ISO week; Apr 7 is the next week.
    render(<DimensionScoreHistoryPanel trend={TREND} dimension="maintainability" granularity="week" />);
    expect(screen.getByText(/· 2w/)).toBeInTheDocument();
  });

  it('renders the PeriodSelect when onGranularityChange is provided and reports changes', () => {
    const onGranularityChange = vi.fn();
    render(
      <DimensionScoreHistoryPanel
        trend={TREND}
        dimension="maintainability"
        granularity="day"
        onGranularityChange={onGranularityChange}
      />,
    );
    const select = screen.getByLabelText(/Group score history by/i);
    fireEvent.change(select, { target: { value: 'month' } });
    expect(onGranularityChange).toHaveBeenCalledWith('month');
  });

  it('omits the PeriodSelect when onGranularityChange is absent', () => {
    render(<DimensionScoreHistoryPanel trend={TREND} dimension="maintainability" />);
    expect(screen.queryByLabelText(/Group score history by/i)).toBeNull();
  });

  it('applies each bar Cell\'s fill/opacity to the rendered bar (not the SVG black default)', () => {
    stubChartLayout();
    const { container } = render(<DimensionScoreHistoryPanel trend={TREND} dimension="maintainability" />);
    const bars = container.querySelectorAll('.recharts-bar-rectangle .recharts-rectangle');
    expect(bars.length).toBe(3);
    bars.forEach((bar) => {
      // The Cell's fill/opacity/stroke props must land on the path. If Cell
      // is nested inside a wrapper component instead of being Bar's direct
      // child, recharts never applies these and the attributes are absent
      // entirely, leaving the browser's SVG default fill (black).
      expect(bar.getAttribute('fill')).not.toBeNull();
      expect(bar.getAttribute('opacity')).toBe('0.4');
    });
  });
});
