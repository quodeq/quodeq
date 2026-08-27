import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HistorySkeleton from './HistorySkeleton.jsx';

// Footprint stand-in for the loaded history page: the chart panel (reusing
// the existing HistoryChartPanelPlaceholder shell) plus evaluations-table
// rows. Replaces the floating inline spinner so the chart and table swap
// in place instead of popping in below the header.
describe('HistorySkeleton', () => {
  it('reserves the chart panel with the real shell classes', () => {
    const { container } = render(<HistorySkeleton />);
    expect(container.querySelector('.run-history-panel.run-history-panel--terminal.panel')).toBeTruthy();
    expect(container.querySelector('[data-testid="history-chart-panel-placeholder"]')).toBeTruthy();
  });

  it('renders evaluations-table placeholder rows below the chart', () => {
    const { container } = render(<HistorySkeleton />);
    expect(container.querySelectorAll('.history-skeleton__row').length).toBe(6);
  });

  it('is quiet: aria-busy container, aria-hidden, no spinner', () => {
    const { container } = render(<HistorySkeleton />);
    const root = container.querySelector('.history-skeleton');
    expect(root).toHaveAttribute('aria-busy', 'true');
    expect(root).toHaveAttribute('aria-hidden', 'true');
    expect(container.querySelector('.loading-screen')).toBeFalsy();
  });
});
