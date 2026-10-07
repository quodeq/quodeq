import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { RunBar } from './ReEvaluateCardParts.jsx';

// The run bar says what the scan will cover in one line, and the button
// carries how much it will analyze. With nothing to analyze it says so and
// waits, unless the scan is clean (which re-reads everything).
const est = {
  projectFiles: 3892, changedFiles: 3892, dimensions: {
    security: { count: 0, total: 3892, cached: 3892 },
    accessibility: { count: 3892, total: 3892, cached: 0 },
  },
};
const renderBar = (p) => render(
  <RunBar disabled={false} canStart handleScan={vi.fn()} timeLimitS={600} hasModel cleanScan="off" estimates={est} {...p} />,
);
const scan = () => screen.getByRole('button', { name: /scan/i });

describe('RunBar', () => {
  it('one line, the count in the button', () => {
    renderBar({ selectedDims: new Set(['security', 'accessibility']) });
    expect(screen.getByText('2 dimensions · 10:00 total budget')).toBeInTheDocument();
    expect(scan()).toHaveTextContent('3,892 files');
    expect(scan()).toBeEnabled();
    expect(screen.queryByText(/changed files this run|file-analyses queued/)).toBeNull();
  });

  it('nothing to analyze disables scan and says why', () => {
    renderBar({ selectedDims: new Set(['security']) });
    expect(scan()).toBeDisabled();
    expect(scan()).toHaveTextContent('up to date');
    expect(screen.getByText(/pick clean scan/)).toBeInTheDocument();
  });

  it('clean scan is never "up to date"', () => {
    renderBar({ selectedDims: new Set(['security']), cleanScan: 'once' });
    expect(scan()).toBeEnabled();
    expect(scan()).toHaveTextContent('3,892 files');
  });

  it('before estimates land the button carries no count and stays enabled', () => {
    renderBar({ selectedDims: new Set(['security']), estimates: null });
    expect(scan()).toBeEnabled();
    expect(scan()).not.toHaveTextContent(/files|up to date/);
  });

  it('still names the blocker when no model or no dimension is chosen', () => {
    const { rerender } = renderBar({ selectedDims: new Set(), hasModel: true });
    expect(screen.getByText(/pick at least one dimension/)).toBeInTheDocument();
    rerender(<RunBar disabled={false} canStart handleScan={vi.fn()} timeLimitS={600} hasModel={false} cleanScan="off" estimates={est} selectedDims={new Set(['security'])} />);
    expect(screen.getByText(/no model selected/)).toBeInTheDocument();
  });
});
