import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import GradeBoundaryBar from './GradeBoundaryBar.jsx';

// thresholds descending: [[9,'Exemplary'],[7,'Good'],[5,'Adequate'],[3,'Poor']]
// ascending boundaries: [3, 5, 7, 9]
const THRESHOLDS = [
  [9, 'Exemplary'],
  [7, 'Good'],
  [5, 'Adequate'],
  [3, 'Poor'],
];

describe('GradeBoundaryBar slider keyboard accessibility (#1583)', () => {
  it('all dividers have tabIndex=0', () => {
    render(<GradeBoundaryBar thresholds={THRESHOLDS} onChange={vi.fn()} />);
    const sliders = screen.getAllByRole('slider');
    // 4 thresholds => 4 ascending boundaries => 4 dividers (one per segment except last)
    expect(sliders.length).toBe(4);
    sliders.forEach((s) => expect(s).toHaveAttribute('tabindex', '0'));
  });

  it('dividers have aria-valuemin=0 and aria-valuemax=10', () => {
    render(<GradeBoundaryBar thresholds={THRESHOLDS} onChange={vi.fn()} />);
    const sliders = screen.getAllByRole('slider');
    sliders.forEach((s) => {
      expect(s).toHaveAttribute('aria-valuemin', '0');
      expect(s).toHaveAttribute('aria-valuemax', '10');
    });
  });

  it('divider has aria-valuenow matching its boundary value', () => {
    render(<GradeBoundaryBar thresholds={THRESHOLDS} onChange={vi.fn()} />);
    const sliders = screen.getAllByRole('slider');
    // ascending [3,5,7,9]
    expect(sliders[0]).toHaveAttribute('aria-valuenow', '3');
    expect(sliders[1]).toHaveAttribute('aria-valuenow', '5');
    expect(sliders[2]).toHaveAttribute('aria-valuenow', '7');
    expect(sliders[3]).toHaveAttribute('aria-valuenow', '9');
  });

  it('ArrowRight on first divider increments and calls onChange', () => {
    const onChange = vi.fn();
    render(<GradeBoundaryBar thresholds={THRESHOLDS} onChange={onChange} />);
    const sliders = screen.getAllByRole('slider');
    fireEvent.keyDown(sliders[0], { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledTimes(1);
    const newThresholds = onChange.mock.calls[0][0];
    // ascending boundary 0 (was 3) should have increased
    const newAsc = [...newThresholds].map(([t]) => t).reverse();
    expect(newAsc[0]).toBeGreaterThan(3);
  });

  it('ArrowLeft on first divider decrements and calls onChange', () => {
    // Use a boundary with room to decrease: [2,5,7,9]
    const thresholds = [[9,'Exemplary'],[7,'Good'],[5,'Adequate'],[2,'Poor']];
    const onChange = vi.fn();
    render(<GradeBoundaryBar thresholds={thresholds} onChange={onChange} />);
    const sliders = screen.getAllByRole('slider');
    fireEvent.keyDown(sliders[0], { key: 'ArrowLeft' });
    expect(onChange).toHaveBeenCalledTimes(1);
    const newThresholds = onChange.mock.calls[0][0];
    const newAsc = [...newThresholds].map(([t]) => t).reverse();
    expect(newAsc[0]).toBeLessThan(2);
  });

  it('ArrowUp on divider increments same as ArrowRight', () => {
    const onChange = vi.fn();
    render(<GradeBoundaryBar thresholds={THRESHOLDS} onChange={onChange} />);
    const sliders = screen.getAllByRole('slider');
    fireEvent.keyDown(sliders[0], { key: 'ArrowUp' });
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('ArrowDown on divider decrements same as ArrowLeft', () => {
    const thresholds = [[9,'Exemplary'],[7,'Good'],[5,'Adequate'],[2,'Poor']];
    const onChange = vi.fn();
    render(<GradeBoundaryBar thresholds={thresholds} onChange={onChange} />);
    const sliders = screen.getAllByRole('slider');
    fireEvent.keyDown(sliders[0], { key: 'ArrowDown' });
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
