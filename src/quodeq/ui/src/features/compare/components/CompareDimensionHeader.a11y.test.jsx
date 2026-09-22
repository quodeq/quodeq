import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CompareDimensionHeader, { DIMENSION_PANEL_ID, dimensionTabId } from './CompareDimensionHeader.jsx';

const board = [
  { key: 'security', label: 'Security' },
  { key: 'maintainability', label: 'Maintainability' },
];

const view = {
  key: 'maintainability',
  label: 'Maintainability',
  principles: [{ key: 'modularity' }],
  standings: [{ id: 'alpha' }],
  violations: 12,
  avg: 7.5,
  delta: 0.4,
};

describe('CompareDimensionHeader accessibility (#6521)', () => {
  it('exposes the dimension switcher as a labelled tablist', () => {
    render(<CompareDimensionHeader view={view} board={board} onOpenDimension={vi.fn()} />);
    expect(screen.getByRole('tablist', { name: 'Compare dimension' })).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(board.length);
  });

  it('marks the open dimension as the selected tab', () => {
    render(<CompareDimensionHeader view={view} board={board} onOpenDimension={vi.fn()} />);
    expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('Maint');
    expect(screen.getByRole('tab', { name: 'Security' })).toHaveAttribute('aria-selected', 'false');
  });

  it('names each tab after the whole dimension, not the truncated label', () => {
    render(<CompareDimensionHeader view={view} board={board} onOpenDimension={vi.fn()} />);
    // The visible text is clipped to five characters; the accessible name
    // must still be the dimension's real name.
    expect(screen.getByRole('tab', { name: 'Maintainability' })).toHaveTextContent('Maint');
  });

  it('points every tab at the panel it swaps, and identifies itself', () => {
    render(<CompareDimensionHeader view={view} board={board} onOpenDimension={vi.fn()} />);
    const selected = screen.getByRole('tab', { selected: true });
    expect(selected).toHaveAttribute('id', dimensionTabId('maintainability'));
    expect(selected).toHaveAttribute('aria-controls', DIMENSION_PANEL_ID);
    expect(screen.getByRole('tab', { name: 'Security' }))
      .toHaveAttribute('aria-controls', DIMENSION_PANEL_ID);
  });
});
