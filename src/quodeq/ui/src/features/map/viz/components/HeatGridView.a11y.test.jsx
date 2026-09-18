/**
 * Accessibility tests for HeatGridView.
 * 6476: the role="button" name cell activated on Enter only, so Space did
 * nothing. Both keys now go through activateOnKey, for rows and for the
 * sortable header cells.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HeatGridView from './HeatGridView.jsx';

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

function renderGrid(props = {}) {
  return render(
    <HeatGridView node={NODE} onDrillDown={vi.fn()} onFileClick={vi.fn()} {...props} />
  );
}

describe('HeatGridView row activation (6476)', () => {
  it('Space on a drillable folder row calls onDrillDown', () => {
    const onDrillDown = vi.fn();
    renderGrid({ onDrillDown });
    fireEvent.keyDown(screen.getByText('a'), { key: ' ' });
    expect(onDrillDown).toHaveBeenCalledWith('root/a/');
  });

  it('Space on a file row calls onFileClick', () => {
    const onFileClick = vi.fn();
    renderGrid({ onFileClick });
    fireEvent.keyDown(screen.getByText('b.js'), { key: ' ' });
    expect(onFileClick).toHaveBeenCalled();
  });

  it('Enter on a drillable folder row still calls onDrillDown', () => {
    const onDrillDown = vi.fn();
    renderGrid({ onDrillDown });
    fireEvent.keyDown(screen.getByText('a'), { key: 'Enter' });
    expect(onDrillDown).toHaveBeenCalledWith('root/a/');
  });

  it('an unrelated key on a row does not activate it', () => {
    const onDrillDown = vi.fn();
    renderGrid({ onDrillDown });
    fireEvent.keyDown(screen.getByText('a'), { key: 'Tab' });
    expect(onDrillDown).not.toHaveBeenCalled();
  });

  it('Space on a column header still sorts it', () => {
    renderGrid();
    const header = screen.getByText((text) => text.startsWith('Health'));
    fireEvent.keyDown(header, { key: ' ' });
    expect(header.closest('th')).toHaveAttribute('aria-sort', 'descending');
  });
});
