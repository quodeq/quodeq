import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { EvaluationsTable } from './EvaluationsTable.jsx';
import { useHistoryRunLive } from '../hooks/useHistoryRunLive.js';

// Regression coverage for the "No standards fully evaluated yet" bug: an
// in-progress row must become clickable once hasScoredDimension flips true
// (the poll-based, SSE-independent signal), not just from hasScoredDims
// (a static stub, always false) or SSE-only liveCount.
vi.mock('../hooks/useHistoryRunLive.js', () => ({
  useHistoryRunLive: vi.fn(() => ({ liveDims: {}, plannedDimensions: [], hasScoredDimension: false })),
}));

const inProgressEntry = { runId: 'run-1', status: 'in_progress', hasScoredDims: false };

function renderTable(props = {}) {
  return render(
    <EvaluationsTable
      visible={[inProgressEntry]}
      selectedRunId={null}
      deltas={[]}
      statusByRunId={new Map()}
      onRunClick={vi.fn()}
      onRunHover={vi.fn()}
      onRunHoverEnd={vi.fn()}
      onDeleteRun={vi.fn()}
      onNotReadyClick={vi.fn()}
      {...props}
    />,
  );
}

describe('EvaluationsTable in-progress row readiness', () => {
  beforeEach(() => {
    useHistoryRunLive.mockReset();
  });

  it('is not clickable and fires onNotReadyClick when nothing has scored yet', () => {
    useHistoryRunLive.mockReturnValue({ liveDims: {}, plannedDimensions: [], hasScoredDimension: false });
    const onRunClick = vi.fn();
    const onNotReadyClick = vi.fn();
    renderTable({ onRunClick, onNotReadyClick });

    const row = screen.getByRole('button'); // header row uses role="row" (no onClick), so this is the one data row
    fireEvent.click(row);

    expect(onNotReadyClick).toHaveBeenCalledTimes(1);
    expect(onRunClick).not.toHaveBeenCalled();
    expect(row.className).toContain('history-row--not-ready');
  });

  it('becomes clickable once hasScoredDimension is true, even though hasScoredDims and liveCount are both falsy', () => {
    useHistoryRunLive.mockReturnValue({ liveDims: {}, plannedDimensions: [], hasScoredDimension: true });
    const onRunClick = vi.fn();
    const onNotReadyClick = vi.fn();
    renderTable({ onRunClick, onNotReadyClick });

    const row = screen.getByRole('button');
    fireEvent.click(row);

    expect(onRunClick).toHaveBeenCalledWith('run-1');
    expect(onNotReadyClick).not.toHaveBeenCalled();
    expect(row.className).not.toContain('history-row--not-ready');
  });

  it('is already clickable from SSE liveCount alone (unchanged behavior)', () => {
    useHistoryRunLive.mockReturnValue({
      liveDims: { security: { dimension: 'security', score: 8.1 } },
      plannedDimensions: ['security'],
      hasScoredDimension: false,
    });
    const onRunClick = vi.fn();
    renderTable({ onRunClick });

    const row = screen.getByRole('button');
    fireEvent.click(row);

    expect(onRunClick).toHaveBeenCalledWith('run-1');
  });
});
