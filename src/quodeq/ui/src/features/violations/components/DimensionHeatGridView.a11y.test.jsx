/**
 * Accessibility tests for DimensionHeatGridView.
 * 6432: the sortable column header must be a real button with a
 * "Sort by {column}" name, and the <th> must carry aria-sort.
 * 6433: the dimension/principle row is a role="button" widget, so Space has
 * to activate it, not just Enter.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DimensionHeatGridView from './DimensionHeatGridView.jsx';

const DIMENSIONS = [
  {
    dimension: 'security',
    violations: [
      { principle: 'Auth', severity: 'critical', file: 'a.py' },
      { principle: 'Auth', severity: 'major', file: 'b.py' },
    ],
    compliance: [{ principle: 'Auth', file: 'c.py' }],
  },
];

function renderGrid(props = {}) {
  return render(
    <DimensionHeatGridView
      dimensions={DIMENSIONS}
      onDimensionClick={vi.fn()}
      onPrincipleClick={vi.fn()}
      onCellClick={vi.fn()}
      {...props}
    />
  );
}

describe('DimensionHeatGridView sortable header (6432)', () => {
  it('renders each column header as a button named "Sort by {column}"', () => {
    renderGrid();
    expect(screen.getByRole('button', { name: 'Sort by Violations' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sort by Health' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sort by Dimension / Principle' })).toBeInTheDocument();
  });

  it('marks the active column with aria-sort and the others with none', () => {
    renderGrid();
    const active = screen.getByRole('button', { name: 'Sort by Violations' }).closest('th');
    const other = screen.getByRole('button', { name: 'Sort by Health' }).closest('th');
    expect(active).toHaveAttribute('aria-sort', 'descending');
    expect(other).toHaveAttribute('aria-sort', 'none');
  });

  it('activating the header button from the keyboard sorts the column', () => {
    renderGrid();
    const button = screen.getByRole('button', { name: 'Sort by Health' });
    fireEvent.click(button);
    expect(button.closest('th')).toHaveAttribute('aria-sort', 'descending');
    fireEvent.click(button);
    expect(button.closest('th')).toHaveAttribute('aria-sort', 'ascending');
  });
});

describe('DimensionHeatGridView row activation (6433)', () => {
  it('Space on a dimension row calls onDimensionClick', () => {
    const onDimensionClick = vi.fn();
    renderGrid({ onDimensionClick });
    fireEvent.keyDown(screen.getByText('security'), { key: ' ' });
    expect(onDimensionClick).toHaveBeenCalledTimes(1);
  });

  it('Enter on a principle row still calls onPrincipleClick', () => {
    const onPrincipleClick = vi.fn();
    renderGrid({ onPrincipleClick });
    fireEvent.keyDown(screen.getByText('Auth'), { key: 'Enter' });
    expect(onPrincipleClick).toHaveBeenCalledTimes(1);
  });

  it('an unrelated key on a dimension row does not activate it', () => {
    const onDimensionClick = vi.fn();
    renderGrid({ onDimensionClick });
    fireEvent.keyDown(screen.getByText('security'), { key: 'Tab' });
    expect(onDimensionClick).not.toHaveBeenCalled();
  });
});
