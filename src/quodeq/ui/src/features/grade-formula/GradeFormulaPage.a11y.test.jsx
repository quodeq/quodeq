/**
 * #6033 - the FORMULA/TYPES/DIMENSIONS tab strip had no ARIA
 * tab semantics: no role="tablist"/"tab", no aria-selected, no
 * role="tabpanel" on the body it controls.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

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

function Providers({ children }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}><ApiProvider value={{}}>{children}</ApiProvider></QueryClientProvider>;
}

function mount(ui) {
  return render(ui, { wrapper: Providers });
}

describe('GradeFormulaPage tab widget a11y', () => {
  beforeEach(() => { mockHook(); });
  afterEach(() => { vi.clearAllMocks(); });

  it('exposes the tab strip as a labelled tablist', () => {
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('tablist', { name: 'Grade formula view' })).toBeInTheDocument();
  });

  it('marks the active tab as selected and switches selection on click', () => {
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getAllByRole('tab').map((el) => el.textContent)).toEqual(['FORMULA', 'TYPES', 'DIMENSIONS']);
    expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('FORMULA');
    fireEvent.click(screen.getByRole('tab', { name: 'DIMENSIONS' }));
    expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('DIMENSIONS');
  });

  it('renders the active tab body as a tabpanel', () => {
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    expect(screen.getByRole('tabpanel')).toBeInTheDocument();
  });

  // #6033 - complete the tab pattern: each tab points at the
  // panel it controls, and the panel is labelled by whichever tab is active.
  it('wires aria-controls from the active tab to the panel, and aria-labelledby back', () => {
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    const tab = screen.getByRole('tab', { selected: true });
    const panel = screen.getByRole('tabpanel');
    expect(tab).toHaveAttribute('aria-controls', panel.id);
    expect(panel).toHaveAttribute('aria-labelledby', tab.id);
  });

  it('updates aria-controls/aria-labelledby when the active tab changes', () => {
    mount(<GradeFormulaPage navigation={{ selectedProject: 'proj-1' }} />);
    fireEvent.click(screen.getByRole('tab', { name: 'DIMENSIONS' }));
    const tab = screen.getByRole('tab', { selected: true });
    const panel = screen.getByRole('tabpanel');
    expect(tab).toHaveTextContent('DIMENSIONS');
    expect(tab).toHaveAttribute('aria-controls', panel.id);
    expect(panel).toHaveAttribute('aria-labelledby', tab.id);
  });
});
