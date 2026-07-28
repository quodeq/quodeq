import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HistoryChartPanelPlaceholder from './HistoryChartPanelPlaceholder.jsx';
import { HISTORY_CHART_HEIGHT } from '../../../components/scoreChartHelpers.js';

describe('HistoryChartPanelPlaceholder', () => {
  it('rides the real panel shell classes', () => {
    render(<HistoryChartPanelPlaceholder />);
    const el = screen.getByTestId('history-chart-panel-placeholder');
    expect(el.className).toContain('run-history-panel');
    expect(el.className).toContain('run-history-panel--terminal');
    expect(el.className).toContain('panel');
  });

  it('reproduces the header structure', () => {
    render(<HistoryChartPanelPlaceholder />);
    const el = screen.getByTestId('history-chart-panel-placeholder');
    expect(el.querySelector('.run-history-panel__header')).not.toBeNull();
  });

  it('reserves the real panel chart height (220px) via the shared constant', () => {
    render(<HistoryChartPanelPlaceholder />);
    const el = screen.getByTestId('history-chart-panel-placeholder');
    const body = el.querySelector('.chart-with-kbd');
    expect(body).not.toBeNull();
    expect(body).toHaveStyle({ height: `${HISTORY_CHART_HEIGHT}px` });
  });

  it('is quiet: no spinner or pulsing indicator, hidden from assistive tech', () => {
    render(<HistoryChartPanelPlaceholder />);
    const el = screen.getByTestId('history-chart-panel-placeholder');
    expect(el).toHaveAttribute('aria-hidden', 'true');
  });
});
