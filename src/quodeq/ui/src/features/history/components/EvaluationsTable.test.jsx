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

const inProgressEntry = { runId: 'run-1', status: 'running', hasScoredDims: false };

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

describe('EvaluationsTable partial row', () => {
  it('shows a cancelled run with its own grade and score, marked partial', () => {
    const entry = {
      runId: 'c1', status: 'cancelled', dateISO: '2026-05-02T10:00:00Z', dateLabel: '2 May 2026',
      runNumericAverage: 6.5, runOverallGrade: 'Adequate', numericAverage: null,
      dimensions: ['security'], dimensionsCount: 1,
      dimensionDetails: [{ dimension: 'security', score: 6.5, grade: 'Adequate', delta: null }],
    };
    renderTable({ visible: [entry], deltas: [null], statusByRunId: new Map([['c1', 'cancelled']]) });

    expect(screen.getByText('6.5')).toBeInTheDocument();
    expect(screen.getByText('partial')).toBeInTheDocument();
  });
});

describe('EvaluationsTable majors and types columns', () => {
  const done = (runId, majors, openTypes) => ({ runId, dateISO: '2026-09-02T10:00:00Z', dateLabel: '2 Sep', runNumericAverage: '8.5', runOverallGrade: 'Good', dimensionDetails: [{ majors, openTypes }] });

  it('shows the counts with their deltas, down reading as good for majors', () => {
    useHistoryRunLive.mockReturnValue({ liveDims: {}, plannedDimensions: [], hasScoredDimension: false });
    renderTable({
      visible: [done('r2', 3, 30), done('r1', 5, 33)],
      deltas: [0.5, null],
      countDeltas: [{ majors: -2, openTypes: -3 }, { majors: null, openTypes: null }],
    });
    expect(screen.getByText('MAJORS')).toBeInTheDocument();
    expect(screen.getByText('TYPES')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
    const majorsDelta = screen.getByText('-2');
    expect(majorsDelta.className).toContain('history-delta--up');
  });

  it('an in-progress row shows placeholders in the count cells', () => {
    useHistoryRunLive.mockReturnValue({ liveDims: {}, plannedDimensions: [], hasScoredDimension: false });
    renderTable({ countDeltas: [{ majors: null, openTypes: null }] });
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(5);
  });
});
