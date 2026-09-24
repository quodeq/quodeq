import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';

const calls = vi.hoisted(() => ({ extremes: 0, sort: 0 }));

vi.mock('./compareMatrixModel.js', async (importOriginal) => {
  const m = await importOriginal();
  return {
    ...m,
    computeMatrixExtremes: (...a) => { calls.extremes += 1; return m.computeMatrixExtremes(...a); },
    sortMatrixRows: (...a) => { calls.sort += 1; return m.sortMatrixRows(...a); },
  };
});

import CompareMatrix from './CompareMatrix.jsx';

const columns = [{ key: 'sec', label: 'Security', avg: 6 }];
const rows = [
  { id: 'a', name: 'A', overall: 7, cells: { sec: { score: 7 } } },
  { id: 'b', name: 'B', overall: 5, cells: { sec: { score: 5 } } },
];

describe('CompareMatrix', () => {
  beforeEach(() => { calls.extremes = 0; calls.sort = 0; });

  it('does not recompute sort or extremes on hover', () => {
    const { container } = render(
      <CompareMatrix ariaLabel="m" header="h" note="n" columns={columns} matrixRows={rows} footOverall={6} />,
    );
    expect(calls.extremes).toBe(1);
    expect(calls.sort).toBe(1);
    const cell = container.querySelector('tbody td.compare-matrix__num:not(.compare-matrix__overall)');
    fireEvent.mouseEnter(cell);
    expect(container.querySelector('.compare-matrix__hovercol')).not.toBeNull();
    expect(calls.extremes).toBe(1);
    expect(calls.sort).toBe(1);
  });

  it('renders once data grows past the guard without a hook-order error', () => {
    const { container, rerender } = render(
      <CompareMatrix ariaLabel="m" header="h" note="n" columns={columns} matrixRows={rows.slice(0, 1)} footOverall={6} />,
    );
    expect(container.querySelector('table')).toBeNull();
    rerender(<CompareMatrix ariaLabel="m" header="h" note="n" columns={columns} matrixRows={rows} footOverall={6} />);
    expect(container.querySelector('table')).not.toBeNull();
  });
});
