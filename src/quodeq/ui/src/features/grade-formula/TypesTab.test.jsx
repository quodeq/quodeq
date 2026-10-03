import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import TypesTab from './TypesTab.jsx';

function typeRow(over = {}) {
  return {
    key: 'maintainability|M-MDF-3', dimension: 'maintainability', principle: 'Modifiability', req: 'M-MDF-3',
    text: 'Small functions', baseline: 4, now: 2, delta: -2, closed: false, violations: [], severity: 'major', weight: '2.0',
    ...over,
  };
}

const ROWS = [
  typeRow(),
  typeRow({ key: 'maintainability|M-MDF-1', req: 'M-MDF-1', text: 'No magic literals', baseline: 2, now: 0, delta: -2, closed: true, severity: null, weight: null }),
  typeRow({ key: 'security|S-INJ-1', dimension: 'security', principle: 'Input', req: 'S-INJ-1', text: 'Escape input', baseline: null, now: 1, delta: null, severity: 'critical', weight: '8.0' }),
];

describe('TypesTab', () => {
  it('groups rows by dimension and principle', () => {
    render(<TypesTab rows={ROWS} loading={false} dimensionFilter={null} setDimensionFilter={vi.fn()} dimensions={['maintainability', 'security']} />);
    const names = screen.getAllByRole('row').map((r) => r.textContent);
    expect(names.findIndex((n) => n.startsWith('maintainability'))).toBeLessThan(names.findIndex((n) => n.startsWith('Modifiability')));
    expect(names.findIndex((n) => n.startsWith('Modifiability'))).toBeLessThan(names.findIndex((n) => n.includes('M-MDF-3')));
    expect(names.some((n) => n.startsWith('security'))).toBe(true);
  });

  it('no baseline reads as words, never a dash', () => {
    render(<TypesTab rows={ROWS} loading={false} dimensionFilter={null} setDimensionFilter={vi.fn()} dimensions={['maintainability', 'security']} />);
    const row = screen.getByText('S-INJ-1').closest('tr');
    expect(within(row).getByText('no baseline')).toBeInTheDocument();
    expect(row.textContent).not.toMatch(/(^|\s)-(\s|$)/);
  });

  it('shows the weight, the severity and the status', () => {
    render(<TypesTab rows={ROWS} loading={false} dimensionFilter={null} setDimensionFilter={vi.fn()} dimensions={['maintainability', 'security']} />);
    const open = screen.getByText('M-MDF-3').closest('tr');
    expect(within(open).getByText('2.0')).toBeInTheDocument();
    expect(within(open).getByText('major')).toBeInTheDocument();
    expect(within(open).getByText('open')).toBeInTheDocument();
    const closed = screen.getByText('M-MDF-1').closest('tr');
    expect(within(closed).getByText('closed')).toBeInTheDocument();
  });

  it('the dimension select filters and says so', () => {
    const setDimensionFilter = vi.fn();
    render(<TypesTab rows={ROWS} loading={false} dimensionFilter={null} setDimensionFilter={setDimensionFilter} dimensions={['maintainability', 'security']} />);
    fireEvent.change(screen.getByLabelText('Dimension'), { target: { value: 'security' } });
    expect(setDimensionFilter).toHaveBeenCalledWith('security');
  });

  it('says when there are no types', () => {
    render(<TypesTab rows={[]} loading={false} dimensionFilter={null} setDimensionFilter={vi.fn()} dimensions={[]} />);
    expect(screen.getByText('No requirement types with findings in this run.')).toBeInTheDocument();
  });
});
