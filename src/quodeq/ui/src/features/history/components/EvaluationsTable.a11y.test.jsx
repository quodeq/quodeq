import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { EvaluationsTable } from './EvaluationsTable.jsx';

const completedEntry = {
  runId: 'r9',
  dateISO: '2026-01-01T00:00:00',
  dateLabel: '1 Jan 2026',
  numericAverage: 8.1,
  overallGrade: 'Good',
};

function renderTable(props = {}) {
  return render(
    <EvaluationsTable
      visible={[completedEntry]}
      selectedRunId={null}
      deltas={[null]}
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

describe('EvaluationsTable row keyboard access and delete discoverability', () => {
  it('activates a row with Space, same as a real button', () => {
    const onRunClick = vi.fn();
    renderTable({ onRunClick });
    const row = document.querySelector('.history-row:not(.history-row--header)');
    fireEvent.keyDown(row, { key: ' ' });
    expect(onRunClick).toHaveBeenCalledWith('r9', '1 Jan 2026');
  });

  it('exposes the delete button in the accessibility tree (not hidden by an aria-hidden ancestor)', () => {
    renderTable({ onDeleteRun: vi.fn() });
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
  });
});
