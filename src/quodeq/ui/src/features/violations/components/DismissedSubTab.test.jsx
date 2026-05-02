import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import DismissedSubTab from './DismissedSubTab.jsx';

const sampleA = { req: 'A1', file: 'a.py', line: 10, severity: 'minor', principle: 'P1' };
const sampleB = { req: 'B1', file: 'b.py', line: 20, severity: 'major', principle: 'P2' };

function setup(items, overrides = {}) {
  const handlers = {
    onRestore: vi.fn(),
    onRestoreAll: vi.fn(),
    onDelete: vi.fn(),
    onDeleteAll: vi.fn(),
    ...overrides,
  };
  render(<DismissedSubTab dismissed={items} {...handlers} />);
  return handlers;
}

describe('DismissedSubTab', () => {
  it('renders Restore and Delete buttons on each card', () => {
    setup([sampleA, sampleB]);
    expect(screen.getAllByRole('button', { name: 'Restore' })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(2);
  });

  it('renders Restore all and Delete all in the header when there are 2+ findings', () => {
    setup([sampleA, sampleB]);
    expect(screen.getByRole('button', { name: 'Restore all' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete all' })).toBeInTheDocument();
  });

  it('does not render Restore all / Delete all when there is exactly one finding', () => {
    setup([sampleA]);
    expect(screen.queryByRole('button', { name: 'Restore all' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete all' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Restore' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('clicking Delete on a card invokes onDelete with the finding', () => {
    const handlers = setup([sampleA, sampleB]);
    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' });
    fireEvent.click(deleteButtons[0]);
    expect(handlers.onDelete).toHaveBeenCalledTimes(1);
    expect(handlers.onDelete).toHaveBeenCalledWith(sampleA);
  });

  it('clicking Delete all invokes onDeleteAll once', () => {
    const handlers = setup([sampleA, sampleB]);
    fireEvent.click(screen.getByRole('button', { name: 'Delete all' }));
    expect(handlers.onDeleteAll).toHaveBeenCalledTimes(1);
  });

  it('renders the empty state when there are no findings', () => {
    render(
      <DismissedSubTab
        dismissed={[]}
        onRestore={vi.fn()}
        onRestoreAll={vi.fn()}
        onDelete={vi.fn()}
        onDeleteAll={vi.fn()}
      />,
    );
    expect(screen.getByText(/No dismissed findings/i)).toBeInTheDocument();
  });
});
