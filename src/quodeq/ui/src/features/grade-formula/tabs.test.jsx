import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import {
  SeverityTab, BoundariesTab, DimensionsTab,
} from './tabs.jsx';
import GradeBoundaryBar from './GradeBoundaryBar.jsx';

const THRESHOLDS = [[9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor']];

function baseDraft(overrides = {}) {
  return {
    severityWeight: { critical: 8, major: 3, minor: 1 },
    baseK: 0.1,
    liftCompress: 2,
    ceilScale: 1,
    floorMinor: 8,
    floorMajor: 5,
    gradeThresholds: THRESHOLDS,
    dimensionWeightsEnabled: false,
    dimensionWeights: { security: 1.2, maintainability: 1 },
    ...overrides,
  };
}

describe('SeverityTab', () => {
  it('changing a slider calls update with a merged severityWeight', () => {
    const update = vi.fn();
    render(<SeverityTab draft={baseDraft()} update={update} />);
    fireEvent.change(screen.getByLabelText('critical'), { target: { value: '6' } });
    expect(update).toHaveBeenCalledWith({
      severityWeight: { critical: 6, major: 3, minor: 1 },
    });
  });

  it('shows the critical-to-minor ratio', () => {
    render(<SeverityTab draft={baseDraft()} update={vi.fn()} />);
    expect(screen.getByText(/weighs 8x a minor one/)).toBeInTheDocument();
  });
});

describe('BoundariesTab floor sliders', () => {
  it('clamps floorMinor so it can not drop below floorMajor', () => {
    const update = vi.fn();
    render(<BoundariesTab draft={baseDraft()} update={update} />);
    // floorMajor is 5; dragging floorMinor down to 3 must clamp up to 5.
    fireEvent.change(screen.getByLabelText('minor only'), { target: { value: '3' } });
    expect(update).toHaveBeenCalledWith({ floorMinor: 5 });
  });

  it('clamps floorMajor so it can not rise above floorMinor', () => {
    const update = vi.fn();
    render(<BoundariesTab draft={baseDraft()} update={update} />);
    // floorMinor is 8; pushing floorMajor up to 10 must clamp down to 8.
    fireEvent.change(screen.getByLabelText('major'), { target: { value: '10' } });
    expect(update).toHaveBeenCalledWith({ floorMajor: 8 });
  });
});

describe('DimensionsTab', () => {
  it('toggle flips dimensionWeightsEnabled', () => {
    const update = vi.fn();
    render(<DimensionsTab draft={baseDraft()} update={update} />);
    fireEvent.click(screen.getByText('apply dimension weights'));
    expect(update).toHaveBeenCalledWith({ dimensionWeightsEnabled: true });
  });

  it('dimension sliders are disabled when weighting is off', () => {
    render(<DimensionsTab draft={baseDraft()} update={vi.fn()} />);
    expect(screen.getByLabelText('security')).toBeDisabled();
    expect(screen.getByLabelText('maintainability')).toBeDisabled();
  });

  it('dimension sliders are enabled when weighting is on', () => {
    render(<DimensionsTab draft={baseDraft({ dimensionWeightsEnabled: true })} update={vi.fn()} />);
    expect(screen.getByLabelText('security')).toBeEnabled();
  });
});

describe('GradeBoundaryBar', () => {
  let rectSpy;

  beforeEach(() => {
    rectSpy = vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
      left: 0, top: 0, right: 100, bottom: 28, width: 100, height: 28, x: 0, y: 0,
      toJSON: () => {},
    });
  });

  afterEach(() => {
    rectSpy.mockRestore();
  });

  it('renders five segments', () => {
    render(<GradeBoundaryBar thresholds={THRESHOLDS} onChange={vi.fn()} />);
    ['CRITICAL', 'POOR', 'ADEQUATE', 'GOOD', 'EXEMPLARY'].forEach((label) => {
      expect(screen.getByText(label)).toBeInTheDocument();
    });
  });

  it('emits a descending thresholds array on a simulated drag', () => {
    const onChange = vi.fn();
    render(<GradeBoundaryBar thresholds={THRESHOLDS} onChange={onChange} />);
    // Boundary 4 is the topmost ascending divider (asc index 3, value 9).
    // Drag it to clientX 80 -> 8.0 on the 0..10 scale (width 100).
    const divider = screen.getByLabelText('Boundary 4');
    fireEvent.pointerDown(divider, { clientX: 90 });
    fireEvent.pointerMove(window, { clientX: 80 });
    fireEvent.pointerUp(window);

    expect(onChange).toHaveBeenCalled();
    const next = onChange.mock.calls.at(-1)[0];
    // Descending values, labels preserved.
    const values = next.map(([t]) => t);
    expect(values).toEqual([8, 7, 5, 3]);
    expect(next.map(([, l]) => l)).toEqual(['Exemplary', 'Good', 'Adequate', 'Poor']);
    // Strictly descending.
    for (let i = 1; i < values.length; i += 1) {
      expect(values[i]).toBeLessThan(values[i - 1]);
    }
  });

  it('clamps a divider against its neighbour with the minimum gap', () => {
    const onChange = vi.fn();
    render(<GradeBoundaryBar thresholds={THRESHOLDS} onChange={onChange} />);
    // Boundary 1 is asc index 0 (value 3); its upper neighbour is 5.
    // Try to drag it to 9.0 -> must clamp to 5 - 0.5 = 4.5.
    const divider = screen.getByLabelText('Boundary 1');
    fireEvent.pointerDown(divider, { clientX: 30 });
    fireEvent.pointerMove(window, { clientX: 90 });
    fireEvent.pointerUp(window);

    const next = onChange.mock.calls.at(-1)[0];
    // ascending [4.5, 5, 7, 9] -> descending [9, 7, 5, 4.5]
    expect(next.map(([t]) => t)).toEqual([9, 7, 5, 4.5]);
  });

  it('removes all window listeners after pointercancel so subsequent moves are silent', () => {
    const onChange = vi.fn();
    render(<GradeBoundaryBar thresholds={THRESHOLDS} onChange={onChange} />);
    const divider = screen.getByLabelText('Boundary 2');
    fireEvent.pointerDown(divider, { clientX: 50 });
    // One move during the drag — onChange fires.
    fireEvent.pointerMove(window, { clientX: 55 });
    expect(onChange).toHaveBeenCalledTimes(1);
    // Browser cancels the gesture (e.g. touch pan taken over by scroll).
    fireEvent.pointerCancel(window);
    // Further moves after cancel must NOT fire onChange.
    fireEvent.pointerMove(window, { clientX: 60 });
    fireEvent.pointerMove(window, { clientX: 70 });
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
