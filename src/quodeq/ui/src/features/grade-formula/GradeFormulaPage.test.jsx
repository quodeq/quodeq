import {
  describe, it, expect, vi, beforeEach, afterEach,
} from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// The page composes the editor hook + tab bodies. We mock the hook so the
// test controls draft/dirty/busy without touching the network, and assert the
// page-level wiring: header, tab switching, action gating, confirm dialogs,
// and the busy guard.
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

describe('GradeFormulaPage', () => {
  let confirmSpy;

  beforeEach(() => {
    confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  afterEach(() => {
    confirmSpy.mockRestore();
    vi.clearAllMocks();
  });

  it('shows a loading header until the draft arrives', () => {
    mockHook({ draft: null });
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByText('loading')).toBeInTheDocument();
  });

  it('renders the severity tab first and switches tabs on click', () => {
    mockHook();
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    // Severity tab body shows the critical slider.
    expect(screen.getByLabelText('critical')).toBeInTheDocument();
    // Switch to Dimensions: its toggle button appears, severity slider goes away.
    fireEvent.click(screen.getByRole('button', { name: 'DIMENSIONS' }));
    expect(screen.getByText('apply dimension weights')).toBeInTheDocument();
    expect(screen.queryByLabelText('critical')).not.toBeInTheDocument();
  });

  it('disables APPLY when the draft is clean and enables it when dirty', () => {
    mockHook({ isDirty: false });
    const { rerender } = render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('button', { name: 'APPLY' })).toBeDisabled();

    mockHook({ isDirty: true });
    rerender(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('button', { name: 'APPLY' })).toBeEnabled();
  });

  it('APPLY confirms then calls apply', async () => {
    const state = mockHook({ isDirty: true });
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'APPLY' }));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(state.apply).toHaveBeenCalledTimes(1);
  });

  it('RESET confirms then calls resetToDefaults', () => {
    const state = mockHook();
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    fireEvent.click(screen.getByRole('button', { name: /RESET/ }));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(state.resetToDefaults).toHaveBeenCalledTimes(1);
  });

  it('a cancelled APPLY confirm does not call apply', () => {
    confirmSpy.mockReturnValue(false);
    const state = mockHook({ isDirty: true });
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'APPLY' }));
    expect(state.apply).not.toHaveBeenCalled();
  });

  it('busy disables the action buttons and the tab body fieldset', () => {
    mockHook({ busy: true, isDirty: true });
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('button', { name: 'APPLY' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /RESET/ })).toBeDisabled();
    // The busy guard cascades to inputs inside the disabled fieldset.
    expect(screen.getByLabelText('critical')).toBeDisabled();
  });

  it('shows the no-project empty hint when no project is selected', () => {
    mockHook();
    render(<GradeFormulaPage navigation={{ selectedProject: null }} />);
    expect(screen.getByText('Select a project to see a live preview.')).toBeInTheDocument();
  });

  it('shows the per-project empty hint when a project is selected but preview is empty', () => {
    mockHook({ preview: null });
    render(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(
      screen.getByText('No evaluation with an event log yet. Run an evaluation to see a live preview.'),
    ).toBeInTheDocument();
  });
});
