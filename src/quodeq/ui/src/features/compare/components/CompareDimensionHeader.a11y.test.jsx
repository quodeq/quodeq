import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CompareDimensionHeader from './CompareDimensionHeader.jsx';

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
    expect(screen.getByRole('tab', { name: 'Secur' })).toHaveAttribute('aria-selected', 'false');
  });
});
