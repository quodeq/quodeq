import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import RiskMatrixView from './RiskMatrixView.jsx';

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
      severity: { critical: 1, major: 1, minor: 1 },
      children: [{}],
    },
    {
      path: 'root/b.js',
      name: 'b.js',
      isFile: true,
      violations: 1,
      compliance: 0,
      severity: { critical: 0, major: 1, minor: 0 },
      children: [],
    },
  ],
};

describe('RiskMatrixView drillable circle keyboard accessibility (#1936)', () => {
  function getDrillableCircle(container) {
    // The drillable circle is the one with role="button"
    return container.querySelector('circle[role="button"]');
  }

  it('drillable circle has tabIndex=0', () => {
    const { container } = render(<RiskMatrixView node={NODE} onDrillDown={vi.fn()} />);
    const circle = getDrillableCircle(container);
    expect(circle).not.toBeNull();
    expect(circle).toHaveAttribute('tabindex', '0');
  });

  it('drillable circle carries the viz-focusable class (suppresses stray focus ring)', () => {
    const { container } = render(<RiskMatrixView node={NODE} onDrillDown={vi.fn()} />);
    const circle = getDrillableCircle(container);
    expect(circle).toHaveClass('viz-focusable');
  });

  it('drillable circle has role="button"', () => {
    const { container } = render(<RiskMatrixView node={NODE} onDrillDown={vi.fn()} />);
    const circle = getDrillableCircle(container);
    expect(circle).toHaveAttribute('role', 'button');
  });

  it('drillable circle has aria-label', () => {
    const { container } = render(<RiskMatrixView node={NODE} onDrillDown={vi.fn()} />);
    const circle = getDrillableCircle(container);
    expect(circle).toHaveAttribute('aria-label');
    expect(circle.getAttribute('aria-label').length).toBeGreaterThan(0);
  });

  it('Enter key on drillable circle calls onDrillDown', () => {
    const onDrillDown = vi.fn();
    const { container } = render(<RiskMatrixView node={NODE} onDrillDown={onDrillDown} />);
    const circle = getDrillableCircle(container);
    fireEvent.keyDown(circle, { key: 'Enter' });
    expect(onDrillDown).toHaveBeenCalledTimes(1);
    expect(onDrillDown).toHaveBeenCalledWith('root/a/');
  });

  it('Space key on drillable circle calls onDrillDown', () => {
    const onDrillDown = vi.fn();
    const { container } = render(<RiskMatrixView node={NODE} onDrillDown={onDrillDown} />);
    const circle = getDrillableCircle(container);
    fireEvent.keyDown(circle, { key: ' ' });
    expect(onDrillDown).toHaveBeenCalledTimes(1);
  });
});
