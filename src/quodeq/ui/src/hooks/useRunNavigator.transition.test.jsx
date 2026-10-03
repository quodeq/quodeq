import { describe, it, expect } from 'vitest';
import { Suspense, useState } from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useRunNavigator } from './useRunNavigator.js';

const RUNS = [{ runId: 'r1' }, { runId: 'r2' }, { runId: 'r3' }];

// Suspends forever for any run other than the first: stands in for the
// dashboard queries that a run switch kicks off.
const pending = new Promise(() => {});
function RunContent({ runId }) {
  if (runId !== 'r1') throw pending;
  return <p>content for {runId}</p>;
}

function Harness() {
  const [selectedRun, setSelectedRun] = useState('r1');
  const nav = useRunNavigator({ selectedRun, availableRuns: RUNS, onRunChange: setSelectedRun, onNavigate: () => {} });
  return (
    <div>
      <output data-testid="highlight">{nav.currentOverviewRun}</output>
      <output data-testid="pending">{String(nav.isRunSwitchPending)}</output>
      <button onClick={() => nav.handleRunSelect('r2')}>pick r2</button>
      <Suspense fallback={<p>fallback</p>}>
        <RunContent runId={selectedRun} />
      </Suspense>
    </div>
  );
}

describe('useRunNavigator run switch as a transition', () => {
  it('moves the highlight at once and keeps the previous content while the new run suspends', async () => {
    render(<Harness />);
    expect(screen.getByText('content for r1')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText('pick r2'));
    });

    expect(screen.getByTestId('highlight')).toHaveTextContent('r2');
    expect(screen.getByTestId('pending')).toHaveTextContent('true');
    // The transition keeps the old tree visible instead of the fallback.
    expect(screen.getByText('content for r1')).toBeInTheDocument();
    expect(screen.queryByText('fallback')).toBeNull();
  });
});
