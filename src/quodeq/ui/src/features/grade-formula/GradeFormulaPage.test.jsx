import {
  describe, it, expect, vi, beforeEach, afterEach,
} from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// The page composes the editor hook + tab bodies. We mock the hook so the
// test controls draft/dirty/busy without touching the network, and assert the
// page-level wiring: header, tab switching, action gating, confirm dialogs,
// and the busy guard.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../api/ApiContext.jsx';
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

const EXPLAIN = {
  runId: 'r1', dimension: 'security', params: { baseK: 0.1 },
  principles: [{ principleId: 'P1', findings: 3, compliance: 4, insufficient: false, stages: { types: { critical: 0, major: 1, minor: 3 }, complianceTypes: 4, weightedViolations: 2.25, base: 7.87, lift: 0.36, raw: 8.64, ceiling: 9.16, floor: 5, final: 8.6, grade: 'Good' } }],
};

function providers(api) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }) => (
    <QueryClientProvider client={client}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>
  );
}

function mount(ui, api = { getGradeExplain: vi.fn(async () => EXPLAIN), previewGradeExplain: vi.fn(async () => EXPLAIN) }) {
  return { ...render(ui, { wrapper: providers(api) }), api };
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
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByText('loading')).toBeInTheDocument();
  });

  it('renders the formula tab first, with the four stage titles, and switches tabs on click', () => {
    mockHook();
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByLabelText('critical')).toBeInTheDocument();
    for (const title of ['Types, weighted', 'Base', 'Lift', 'Ceiling and floors']) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    }
    // Switch to Dimensions: its toggle button appears, severity slider goes away.
    fireEvent.click(screen.getByRole('tab', { name: 'DIMENSIONS' }));
    expect(screen.getByText('apply dimension weights')).toBeInTheDocument();
    expect(screen.queryByLabelText('critical')).not.toBeInTheDocument();
  });

  it('no run: the sliders render without numbers and nothing is fetched', () => {
    mockHook();
    const { api } = mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} scope={{ project: 'proj-1', runId: null, dimensions: [], dimension: null }} />);
    for (const label of ['critical', 'strictness K', 'lift compress', 'ceiling scale']) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
    expect(screen.getAllByText('open a project with a finished run to see its numbers').length).toBeGreaterThan(0);
    expect(api.getGradeExplain).not.toHaveBeenCalled();
  });

  it('the TYPES tab lists the run types with the draft weight', async () => {
    mockHook();
    const runDimensions = [{ dimension: 'security', violations: [{ req: 'S-INJ-1', principle: 'Input', file: 'a.py', line: 1, severity: 'major' }] }];
    mount(
      <GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} scope={{ project: 'proj-1', runId: 'r1', dimensions: ['security'], dimension: null, runDimensions, selectedSource: null }} />,
      { getGradeExplain: vi.fn(async () => EXPLAIN), previewGradeExplain: vi.fn(async () => EXPLAIN), getRunDiff: vi.fn(async () => ({ dimensions: {} })), getStandard: vi.fn(async () => ({ principles: [] })) },
    );
    fireEvent.click(screen.getByRole('tab', { name: 'TYPES' }));
    expect(await screen.findByText('S-INJ-1')).toBeInTheDocument();
    expect(screen.getByText('3.0')).toBeInTheDocument();
    expect(screen.getByText('no baseline')).toBeInTheDocument();
  });

  it('unknown dimension falls back to the first one the scope knows', async () => {
    mockHook();
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} scope={{ project: 'proj-1', runId: 'r1', dimensions: ['security'], dimension: 'nope' }} />);
    expect(screen.getByLabelText('Dimension')).toHaveValue('security');
    expect(await screen.findByText('8.6 Good')).toBeInTheDocument();
  });

  it('disables APPLY when the draft is clean and enables it when dirty', () => {
    mockHook({ isDirty: false });
    const { rerender } = mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('button', { name: 'APPLY' })).toBeDisabled();

    mockHook({ isDirty: true });
    rerender(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('button', { name: 'APPLY' })).toBeEnabled();
  });

  it('APPLY confirms then calls apply', async () => {
    const state = mockHook({ isDirty: true });
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'APPLY' }));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(state.apply).toHaveBeenCalledTimes(1);
  });

  it('RESET confirms then calls resetToDefaults', () => {
    const state = mockHook();
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    fireEvent.click(screen.getByRole('button', { name: /RESET/ }));
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(state.resetToDefaults).toHaveBeenCalledTimes(1);
  });

  it('a cancelled APPLY confirm does not call apply', () => {
    confirmSpy.mockReturnValue(false);
    const state = mockHook({ isDirty: true });
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'APPLY' }));
    expect(state.apply).not.toHaveBeenCalled();
  });

  it('busy disables the action buttons and the tab body fieldset', () => {
    mockHook({ busy: true, isDirty: true });
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('button', { name: 'APPLY' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /RESET/ })).toBeDisabled();
    // The busy guard cascades to inputs inside the disabled fieldset.
    expect(screen.getByLabelText('critical')).toBeDisabled();
  });

  it('shows the no-project empty hint when no project is selected', () => {
    mockHook();
    mount(<GradeFormulaPage navigation={{ selectedProject: null }} />);
    expect(screen.getByText('Select a project to see a live preview.')).toBeInTheDocument();
  });

  it('shows the per-project empty hint when a project is selected but preview is empty', () => {
    mockHook({ preview: null });
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(
      screen.getByText('No evaluation with an event log yet. Run an evaluation to see a live preview.'),
    ).toBeInTheDocument();
  });

  describe('boundary-divider drag guard when busy', () => {
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

    it('blocks boundary-bar drags while busy:true — update is NOT called', () => {
      const state = mockHook({ busy: true });
      mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
      
      const divider = screen.getByLabelText('Boundary 1');
      fireEvent.pointerDown(divider, { clientX: 30 });
      fireEvent.pointerMove(window, { clientX: 70 });
      fireEvent.pointerUp(window);

      expect(state.update).not.toHaveBeenCalled();
    });

    it('allows boundary-bar drags while busy:false — update IS called', () => {
      const state = mockHook({ busy: false });
      mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
      
      const divider = screen.getByLabelText('Boundary 1');
      fireEvent.pointerDown(divider, { clientX: 30 });
      fireEvent.pointerMove(window, { clientX: 50 });
      fireEvent.pointerUp(window);

      expect(state.update).toHaveBeenCalled();
    });
  });

  it('shows rescore progress in a live region and keeps APPLY and the sliders enabled', () => {
    mockHook({ isDirty: true, rescoreProgress: { done: 2, total: 5 } });
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('status')).toHaveTextContent('Rescoring 2 of 5 runs');
    expect(screen.getByRole('button', { name: 'APPLY' })).toBeEnabled();
    expect(screen.getByRole('button', { name: /RESET/ })).toBeEnabled();
    expect(screen.getByLabelText('critical')).toBeEnabled();
  });

  it('shows a plain rescoring message before the pass has counted its runs', () => {
    mockHook({ rescoreProgress: { done: 0, total: 0 } });
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('status')).toHaveTextContent(/^Rescoring…$/);
  });

  it('keeps the rescore live region mounted and empty when no pass runs', () => {
    mockHook({ rescoreProgress: null });
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });
});
