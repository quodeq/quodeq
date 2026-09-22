import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { GridTable, GridRow, GridCell } from './GridTable.jsx';

describe('GridTable ARIA row/cell roles', () => {
  it('keeps role="row" on the header row and puts role="columnheader" on its cells', () => {
    render(
      <GridTable columns="1fr 1fr">
        <GridRow header>
          <GridCell>Name</GridCell>
          <GridCell>Count</GridCell>
        </GridRow>
      </GridTable>,
    );
    const headerRow = screen.getByRole('row');
    expect(within(headerRow).getAllByRole('columnheader')).toHaveLength(2);
  });

  it('renders role="cell" for a body row', () => {
    render(
      <GridTable columns="1fr 1fr">
        <GridRow>
          <GridCell>security</GridCell>
          <GridCell>3</GridCell>
        </GridRow>
      </GridTable>,
    );
    expect(screen.getAllByRole('cell')).toHaveLength(2);
  });
});

describe('GridTable clickable row keyboard activation', () => {
  it('activates onClick with Space, not just Enter', () => {
    const onClick = vi.fn();
    render(
      <GridTable columns="1fr">
        <GridRow onClick={onClick}>
          <GridCell>security</GridCell>
        </GridRow>
      </GridTable>,
    );
    const row = screen.getByRole('row');
    fireEvent.keyDown(row, { key: ' ' });
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
