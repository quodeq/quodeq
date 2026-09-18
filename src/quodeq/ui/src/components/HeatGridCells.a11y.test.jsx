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

describe('HeatGridCells ViolationsCell accessible name', () => {
  it('labels the clickable count with the count and the row name', () => {
    const { container } = renderRow(makeRow({ violations: 6, name: 'src/app.js' }));
    const countCell = container.querySelector('.heat-grid-num');
    const name = countCell.getAttribute('aria-label');
    expect(name).toContain('6');
    expect(name).toContain('src/app.js');
  });
});
