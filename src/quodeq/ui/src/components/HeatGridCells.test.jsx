import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HeatGridCells from './HeatGridCells.jsx';

// HeatGridCells renders a run of <td> cells, so it must live inside a table row.
function renderRow(row, props = {}) {
  return render(
    <table>
      <tbody>
        <tr>
          <HeatGridCells row={row} {...props} />
        </tr>
      </tbody>
    </table>
  );
}

function makeRow(overrides = {}) {
  return {
    name: 'src/app.js',
    violations: 6,
    compliance: 4,
    complianceRate: 0.4,
    severity: { critical: 1, major: 2, minor: 3 },
    ...overrides,
  };
}

describe('HeatGridCells', () => {
  it('renders one severity cell per level plus violations and health', () => {
    const { container } = renderRow(makeRow());
    // 3 severity + 1 violations count + 1 health = 5 cells
    expect(container.querySelectorAll('td')).toHaveLength(5);
    expect(screen.getByLabelText('critical: 1 violation in src/app.js')).toHaveTextContent('1');
    expect(screen.getByLabelText('major: 2 violations in src/app.js')).toHaveTextContent('2');
    expect(screen.getByLabelText('minor: 3 violations in src/app.js')).toHaveTextContent('3');
  });

  it('shows the rounded compliance rate as a percentage', () => {
    renderRow(makeRow({ complianceRate: 0.4 }));
    expect(screen.getByText('40%')).toBeInTheDocument();
  });

  it('renders an em dash for the health cell when there is no data', () => {
    renderRow(makeRow({ violations: 0, compliance: 0, complianceRate: 0, severity: { critical: 0, major: 0, minor: 0 } }));
    // Every severity cell and the health cell fall back to the dash.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('makes non-empty severity cells keyboard-focusable buttons with the focus-ring class', () => {
    renderRow(makeRow());
    const critical = screen.getByLabelText('critical: 1 violation in src/app.js');
    expect(critical).toHaveAttribute('role', 'button');
    expect(critical).toHaveAttribute('tabindex', '0');
    expect(critical).toHaveClass('heat-grid-cell', 'clickable', 'viz-focusable');
  });

  it('leaves zero-count severity cells non-interactive', () => {
    renderRow(makeRow({ violations: 5, severity: { critical: 0, major: 2, minor: 3 } }));
    const empty = screen.getByLabelText('critical: 0 violations in src/app.js');
    expect(empty).not.toHaveAttribute('role');
    expect(empty).not.toHaveAttribute('tabindex');
    expect(empty).toHaveClass('empty');
    expect(empty).not.toHaveClass('clickable');
  });

  it('fires onCellClick with the severity on click and on Enter/Space', () => {
    const onCellClick = vi.fn();
    const row = makeRow();
    renderRow(row, { onCellClick });
    const major = screen.getByLabelText('major: 2 violations in src/app.js');

    fireEvent.click(major);
    fireEvent.keyDown(major, { key: 'Enter' });
    fireEvent.keyDown(major, { key: ' ' });

    expect(onCellClick).toHaveBeenCalledTimes(3);
    expect(onCellClick).toHaveBeenCalledWith({ row, severity: 'major' });
  });

  it('fires onCellClick with a null severity from the violations count cell', () => {
    const onCellClick = vi.fn();
    const row = makeRow();
    const { container } = renderRow(row, { onCellClick });
    const countCell = container.querySelector('.heat-grid-num');

    expect(countCell).toHaveClass('clickable', 'viz-focusable');
    expect(countCell).toHaveAttribute('role', 'button');
    expect(countCell).toHaveAttribute('tabindex', '0');

    fireEvent.click(countCell);
    fireEvent.keyDown(countCell, { key: 'Enter' });
    expect(onCellClick).toHaveBeenCalledTimes(2);
    expect(onCellClick).toHaveBeenLastCalledWith({ row, severity: null });
  });

  it('does not make the count cell interactive when there are no violations', () => {
    const onCellClick = vi.fn();
    const { container } = renderRow(makeRow({ violations: 0, severity: { critical: 0, major: 0, minor: 0 } }), { onCellClick });
    const countCell = container.querySelector('.heat-grid-num');
    expect(countCell).not.toHaveClass('clickable');
    expect(countCell).not.toHaveAttribute('role');
    fireEvent.click(countCell);
    expect(onCellClick).not.toHaveBeenCalled();
  });

  it('uses filled cell styling in the default heat variant', () => {
    const { container } = renderRow(makeRow());
    // The heat variant paints the cell background via severityCellStyle, so the
    // inline style carries more than a bare text color.
    const critical = screen.getByLabelText('critical: 1 violation in src/app.js');
    expect(critical.getAttribute('style')).toBeTruthy();
    expect(critical.getAttribute('style')).not.toBe('color: ;');
    // Health cell also carries a filled style in heat mode.
    const health = within(container).getByText('40%');
    expect(health).toHaveClass('health');
  });

  it('uses text-only color styling in the flat variant', () => {
    renderRow(makeRow(), { variant: 'flat' });
    // The flat variant colors the text only — the inline style is a color rule.
    const critical = screen.getByLabelText('critical: 1 violation in src/app.js');
    expect(critical.getAttribute('style')).toMatch(/color:/);
    // Class list is identical across variants; only the styling differs.
    expect(critical).toHaveClass('heat-grid-cell', 'clickable', 'viz-focusable');
  });
});
