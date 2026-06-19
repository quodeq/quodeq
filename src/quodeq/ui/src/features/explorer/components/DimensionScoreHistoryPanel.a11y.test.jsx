import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DimensionScoreHistoryPanel from './DimensionScoreHistoryPanel.jsx';

const TREND = [
  { runId: 'r2', dateLabel: 'Apr 5', dimensionDetails: [{ dimension: 'maintainability', score: 5.7 }] },
  { runId: 'r1', dateLabel: 'Apr 3', dimensionDetails: [{ dimension: 'maintainability', score: 5.2 }] },
];

describe('DimensionScoreHistoryPanel chart keyboard accessibility (#1979)', () => {
  it('chart wrapper has tabIndex=0 when onBarClick is provided', () => {
    const onBarClick = vi.fn();
    render(
      <DimensionScoreHistoryPanel
        trend={TREND}
        dimension="maintainability"
        onBarClick={onBarClick}
      />
    );
    // The chart keyboard wrapper should be focusable
    const wrapper = document.querySelector('[tabindex="0"]');
    expect(wrapper).not.toBeNull();
  });

  it('Enter key on chart wrapper fires onBarClick with last data point', () => {
    const onBarClick = vi.fn();
    render(
      <DimensionScoreHistoryPanel
        trend={TREND}
        dimension="maintainability"
        onBarClick={onBarClick}
      />
    );
    const wrapper = document.querySelector('[tabindex="0"]');
    expect(wrapper).not.toBeNull();
    fireEvent.keyDown(wrapper, { key: 'Enter' });
    expect(onBarClick).toHaveBeenCalledTimes(1);
  });

  it('Space key on chart wrapper fires onBarClick', () => {
    const onBarClick = vi.fn();
    render(
      <DimensionScoreHistoryPanel
        trend={TREND}
        dimension="maintainability"
        onBarClick={onBarClick}
      />
    );
    const wrapper = document.querySelector('[tabindex="0"]');
    fireEvent.keyDown(wrapper, { key: ' ' });
    expect(onBarClick).toHaveBeenCalledTimes(1);
  });

  it('does not add tabIndex when onBarClick is absent', () => {
    render(
      <DimensionScoreHistoryPanel
        trend={TREND}
        dimension="maintainability"
      />
    );
    const wrapper = document.querySelector('[tabindex="0"]');
    expect(wrapper).toBeNull();
  });
});
