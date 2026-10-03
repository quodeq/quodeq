import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import FormulaTab from './FormulaTab.jsx';

const THRESHOLDS = [[9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor']];

function baseDraft(overrides = {}) {
  return {
    severityWeight: { critical: 8, major: 3, minor: 1 },
    baseK: 0.1, liftCompress: 2, ceilScale: 1, floorMinor: 8, floorMajor: 5,
    gradeThresholds: THRESHOLDS,
    dimensionWeightsEnabled: false, dimensionWeights: { security: 1.2 },
    ...overrides,
  };
}

const EMPTY = { stored: null, live: null, note: null };

function row(key, value, label = key) {
  return { key, label, value, param: null, paramValue: null, tab: '' };
}

const ROWS = [row('types', '0 critical, 1 major, 3 minor = 2.25'), row('base', '7.9'), row('lift', '4 compliance types lift 0.36 of the gap'),
  row('raw', '8.6'), row('ceiling', '9.2'), row('floor', '5.0'), row('final', '8.6 Good')];

describe('FormulaTab knobs', () => {
  it('changing a severity slider calls update with a merged severityWeight', () => {
    const update = vi.fn();
    render(<FormulaTab draft={baseDraft()} update={update} stages={EMPTY} />);
    fireEvent.change(screen.getByLabelText('critical'), { target: { value: '6' } });
    expect(update).toHaveBeenCalledWith({ severityWeight: { critical: 6, major: 3, minor: 1 } });
  });

  it('shows the critical-to-minor ratio', () => {
    render(<FormulaTab draft={baseDraft()} update={vi.fn()} stages={EMPTY} />);
    expect(screen.getByText(/weighs 8x a minor one/)).toBeInTheDocument();
  });

  // Clamping lives in gradeFormulaRules.clampFloors; the sliders forward the raw value.
  it('floor sliders forward the raw value to update, unclamped', () => {
    const update = vi.fn();
    render(<FormulaTab draft={baseDraft()} update={update} stages={EMPTY} />);
    fireEvent.change(screen.getByLabelText('minor only'), { target: { value: '3' } });
    expect(update).toHaveBeenCalledWith({ floorMinor: 3 });
    fireEvent.change(screen.getByLabelText('majors, no critical'), { target: { value: '10' } });
    expect(update).toHaveBeenCalledWith({ floorMajor: 10 });
  });
});

describe('FormulaTab live numbers', () => {
  it('shows the note in every stage when there are no rows', () => {
    render(<FormulaTab draft={baseDraft()} update={vi.fn()} stages={{ ...EMPTY, note: 'no run here' }} />);
    expect(screen.getAllByText('no run here')).toHaveLength(4);
  });

  it('shows the stored rows until live ones arrive, without a "was"', () => {
    render(<FormulaTab draft={baseDraft()} update={vi.fn()} stages={{ stored: ROWS, live: null, note: null }} />);
    expect(screen.getByText('8.6 Good')).toBeInTheDocument();
    expect(screen.getByText('7.9')).toBeInTheDocument();
    expect(screen.queryByText(/was /)).not.toBeInTheDocument();
  });

  it('shows the live final with the stored one as "was" when they differ', () => {
    const live = ROWS.map((r) => (r.key === 'final' ? row('final', '7.1 Good') : r));
    render(<FormulaTab draft={baseDraft()} update={vi.fn()} stages={{ stored: ROWS, live, note: null }} />);
    expect(screen.getByText('7.1 Good')).toBeInTheDocument();
    expect(screen.getByText('was 8.6 Good')).toBeInTheDocument();
  });
});
