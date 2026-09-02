import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HeatGridView from './HeatGridView.jsx';

// HeatGridView had zero coverage before this refactor (in-file
// useHeatGridSort + row-component split).
const NODE = {
  path: 'root/',
  name: 'root',
  isFile: false,
  violations: 0,
  compliance: 0,
  severity: {},
  children: [
    {
      path: 'root/a/',
      name: 'a',
      isFile: false,
      violations: 3,
      compliance: 1,
      complianceRate: 0.25,
      severity: { critical: 1, major: 1, minor: 1 },
      children: [{}],
    },
    {
      path: 'root/b.js',
      name: 'b.js',
      isFile: true,
      violations: 1,
      compliance: 2,
      complianceRate: 0.66,
      severity: { critical: 0, major: 1, minor: 0 },
      children: [],
    },
  ],
};

describe('HeatGridView', () => {
  it('renders one row per child, sorted by violations desc by default', () => {
    render(<HeatGridView node={NODE} onDrillDown={vi.fn()} onFileClick={vi.fn()} />);
    const rows = screen.getAllByRole('row');
    // header row + 2 data rows
    expect(rows.length).toBe(3);
    expect(screen.getByText('a')).toBeInTheDocument();
    expect(screen.getByText('b.js')).toBeInTheDocument();
  });

  it('renders the empty state when nothing has violations or compliance', () => {
    render(<HeatGridView node={{ ...NODE, children: [] }} onDrillDown={vi.fn()} onFileClick={vi.fn()} />);
    expect(screen.getByText(/no/i)).toBeInTheDocument();
  });

  it('clicking a drillable folder row calls onDrillDown', () => {
    const onDrillDown = vi.fn();
    render(<HeatGridView node={NODE} onDrillDown={onDrillDown} onFileClick={vi.fn()} />);
    fireEvent.click(screen.getByText('a'));
    expect(onDrillDown).toHaveBeenCalledWith('root/a/');
  });

  it('clicking a file row calls onFileClick', () => {
    const onFileClick = vi.fn();
    render(<HeatGridView node={NODE} onDrillDown={vi.fn()} onFileClick={onFileClick} />);
    fireEvent.click(screen.getByText('b.js'));
    expect(onFileClick).toHaveBeenCalled();
  });

  it('clicking a column header toggles sort direction', () => {
    render(<HeatGridView node={NODE} onDrillDown={vi.fn()} onFileClick={vi.fn()} />);
    const nameHeader = screen.getByText((t) => t.startsWith('File'));
    fireEvent.click(nameHeader);
    expect(nameHeader.closest('th')).toHaveAttribute('aria-sort', 'ascending');
    fireEvent.click(nameHeader);
    expect(nameHeader.closest('th')).toHaveAttribute('aria-sort', 'descending');
  });
});
