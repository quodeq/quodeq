/**
 * #6033 - the SEVERITY/CURVE/BOUNDARIES/DIMENSIONS tab strip had no ARIA
 * tab semantics: no role="tablist"/"tab", no aria-selected, no
 * role="tabpanel" on the body it controls.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

import useGradeFormula from './useGradeFormula.js';
import GradeFormulaPage from './GradeFormulaPage.jsx';

vi.mock('./useGradeFormula.js', () => ({ default: vi.fn() }));

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

function mockHook(over = {}) {
  const hookState = {
    draft: baseDraft(),
    defaults: baseDraft(),
    isCustom: false,
    isDirty: false,
    preview: null,
    busy: false,
    error: null,
    update: vi.fn(),
    apply: vi.fn().mockResolvedValue(1),
    resetToDefaults: vi.fn().mockResolvedValue(undefined),
    ...over,
  };
  useGradeFormula.mockReturnValue(hookState);
  return hookState;
}

describe('GradeFormulaPage tab widget a11y', () => {
  beforeEach(() => { mockHook(); });
  afterEach(() => { vi.clearAllMocks(); });

  it('exposes the tab strip as a labelled tablist', () => {
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('tablist', { name: 'Grade formula view' })).toBeInTheDocument();
  });

  it('marks the active tab as selected and switches selection on click', () => {
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('SEVERITY');
    fireEvent.click(screen.getByRole('tab', { name: 'DIMENSIONS' }));
    expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('DIMENSIONS');
  });

  it('renders the active tab body as a tabpanel', () => {
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('tabpanel')).toBeInTheDocument();
  });
});
