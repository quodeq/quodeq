import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import HeatGridCells from './HeatGridCells.jsx';

function renderRow(row, props = {}) {
  return render(
    <table>
      <tbody>
        <tr>
          <HeatGridCells row={row} {...props} />
        </tr>
      </tbody>
    </table>,
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

function severityLabel(container, sev) {
  const index = { critical: 0, major: 1, minor: 2 }[sev];
  return container.querySelectorAll('.heat-grid-cell')[index].getAttribute('aria-label');
}

describe('HeatGridCells ViolationsCell accessible name', () => {
  it('labels the clickable count with the count and the row name', () => {
    const { container } = renderRow(makeRow({ violations: 6, name: 'src/app.js' }));
    const countCell = container.querySelector('.heat-grid-num');
    const name = countCell.getAttribute('aria-label');
    expect(name).toContain('6');
    expect(name).toContain('src/app.js');
  });

  it('says "1 violation" for a single one', () => {
    const { container } = renderRow(makeRow({ violations: 1 }));
    expect(container.querySelector('.heat-grid-num').getAttribute('aria-label'))
      .toBe('1 violation in src/app.js, open details');
  });

  it('says "3 violations" for three', () => {
    const { container } = renderRow(makeRow({ violations: 3 }));
    expect(container.querySelector('.heat-grid-num').getAttribute('aria-label'))
      .toBe('3 violations in src/app.js, open details');
  });
});

describe('HeatGridCells SeverityCell accessible name', () => {
  it('says "1 violation" for a single one, through the catalog', () => {
    const { container } = renderRow(makeRow({ severity: { critical: 1, major: 3, minor: 0 } }));
    expect(severityLabel(container, 'critical')).toBe('critical: 1 violation in src/app.js');
  });

  it('says "3 violations" for three, through the catalog', () => {
    const { container } = renderRow(makeRow({ severity: { critical: 1, major: 3, minor: 0 } }));
    expect(severityLabel(container, 'major')).toBe('major: 3 violations in src/app.js');
  });

  it('names an unnamed row through the catalog, not a bare English literal', () => {
    const { container } = renderRow(makeRow({ name: '', severity: { critical: 2, major: 0, minor: 0 } }));
    expect(severityLabel(container, 'critical')).toBe('critical: 2 violations in row');
  });
});
