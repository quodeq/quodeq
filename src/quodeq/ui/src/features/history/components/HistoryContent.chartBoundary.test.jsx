import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { ChartErrorBoundary } from './HistoryContent.jsx';

// The boundary used to never clear `failed` once set, so one transient
// chunk-load failure killed the chart for the rest of the page's lifetime.
// It must reset when the trend/selectedRunId props it's keyed on change.
function Boom({ shouldThrow }) {
  if (shouldThrow) throw new Error('chart render failed');
  return <div>chart ok</div>;
}

describe('ChartErrorBoundary', () => {
  it('resets and gives the child another chance when trend/selectedRunId change', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const trendA = [{ runId: 'r1' }];
    const trendB = [{ runId: 'r2' }];

    const { rerender } = render(
      <ChartErrorBoundary trend={trendA} selectedRunId="r1">
        <Boom shouldThrow />
      </ChartErrorBoundary>,
    );
    expect(screen.getByText('The chart could not be displayed.')).toBeInTheDocument();

    // New trend/selectedRunId, and the child no longer throws: the boundary
    // must clear `failed` instead of staying stuck on the old fallback.
    rerender(
      <ChartErrorBoundary trend={trendB} selectedRunId="r2">
        <Boom shouldThrow={false} />
      </ChartErrorBoundary>,
    );
    expect(screen.getByText('chart ok')).toBeInTheDocument();
    expect(screen.queryByText('The chart could not be displayed.')).not.toBeInTheDocument();
    warn.mockRestore();
    error.mockRestore();
  });

  it('stays on the fallback across a re-render that does not change trend/selectedRunId', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const trend = [{ runId: 'r1' }];

    const { rerender } = render(
      <ChartErrorBoundary trend={trend} selectedRunId="r1">
        <Boom shouldThrow />
      </ChartErrorBoundary>,
    );
    expect(screen.getByText('The chart could not be displayed.')).toBeInTheDocument();

    // Same trend/selectedRunId identity, unrelated re-render: must not reset.
    rerender(
      <ChartErrorBoundary trend={trend} selectedRunId="r1">
        <Boom shouldThrow={false} />
      </ChartErrorBoundary>,
    );
    expect(screen.getByText('The chart could not be displayed.')).toBeInTheDocument();
    warn.mockRestore();
    error.mockRestore();
  });
});
