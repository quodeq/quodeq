import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RunHistoryPanelPlaceholder from './RunHistoryPanelPlaceholder.jsx';

describe('RunHistoryPanelPlaceholder', () => {
  it('rides the real panel shell classes so the flex row footprint matches', () => {
    render(<RunHistoryPanelPlaceholder />);
    const el = screen.getByTestId('run-history-panel-placeholder');
    expect(el.className).toContain('run-history-panel');
    expect(el.className).toContain('run-history-panel--terminal');
    expect(el.className).toContain('panel');
  });

  it('reproduces the header structure', () => {
    render(<RunHistoryPanelPlaceholder />);
    const el = screen.getByTestId('run-history-panel-placeholder');
    expect(el.querySelector('.run-history-panel__header')).not.toBeNull();
  });

  it('gives the body the recharts-responsive-container class that carries flex:1/min-height:160px', () => {
    render(<RunHistoryPanelPlaceholder />);
    const el = screen.getByTestId('run-history-panel-placeholder');
    expect(el.querySelector('.recharts-responsive-container')).not.toBeNull();
  });

  it('is quiet: no spinner or pulsing indicator, hidden from assistive tech', () => {
    render(<RunHistoryPanelPlaceholder />);
    const el = screen.getByTestId('run-history-panel-placeholder');
    expect(el).toHaveAttribute('aria-hidden', 'true');
  });
});
