import { describe, expect, it, vi } from 'vitest';
import {
  buildEvalPrincipal, ROUTE_RENDERERS, isSharedSource, shouldBounceToEvaluate, shouldShowEvaluateButton,
  resolveSelectionAfterSharedDisconnect, shouldAutoOpenOnboardingWizard,
} from './App.jsx';

// Pins the contract that App.jsx's ``buildEvalPrincipal`` threads the
// dimension's run id into ``evalPrincipal.runId``. Without it, the dismiss
// POST from PrincipleDetail (when navigated from the Violations or Map
// pages) lands at the backend with no usable ``run_id`` — the rescore
// returns ``null`` and the grade never updates.

describe('buildEvalPrincipal', () => {
  const principleObj = {
    principle: 'Input Validation',
    dimension: 'Security',
    violations: [],
    compliance: [],
  };
  const principleGrade = { score: '7.0/10', grade: 'B' };

  it('threads runId from the originating accumulated dimension', () => {
    const result = buildEvalPrincipal(principleObj, principleGrade, 'run-abc');
    expect(result.runId).toBe('run-abc');
  });

  it('falls back to empty string when no runId is provided', () => {
    const result = buildEvalPrincipal(principleObj, principleGrade);
    expect(result.runId).toBe('');
  });

  it('preserves principle, dimension, score, and grade fields', () => {
    const result = buildEvalPrincipal(principleObj, principleGrade, 'run-abc');
    expect(result.principle).toBe('Input Validation');
    expect(result.dimension).toBe('Security');
    expect(result.score).toBe('7.0/10');
    expect(result.grade).toBe('B');
  });
});

// Task 19 — read-only gating for shared projects. Shared projects have no
// mutation route on the backend (dismiss/restore/delete/evaluate are
// local-only by design, and a shared project's id can collide with a local
// one). These pin the source-gating contract at the seams App.jsx actually
// wires up, without mounting the whole App (which needs ~8 providers).

describe('isSharedSource', () => {
  it('is true for "shared"', () => expect(isSharedSource('shared')).toBe(true));
  it('is false for "local"', () => expect(isSharedSource('local')).toBe(false));
  it('is false for undefined', () => expect(isSharedSource(undefined)).toBe(false));
});

describe('shouldShowEvaluateButton', () => {
  it('shows Evaluate when projects exist and source is local', () => {
    expect(shouldShowEvaluateButton(3, 'local')).toBe(true);
  });
  it('hides Evaluate for a shared selection even with projects present', () => {
    expect(shouldShowEvaluateButton(3, 'shared')).toBe(false);
  });
  it('hides Evaluate when there are no projects at all', () => {
    expect(shouldShowEvaluateButton(0, 'local')).toBe(false);
  });
});

describe('shouldBounceToEvaluate', () => {
  const base = {
    projectsLoaded: true,
    projectsCount: 2,
    selectedProjectInfo: { runsCount: 0 },
    hasCurrentProjectRuns: false,
    activeTab: 'overview',
    selectedSource: 'local',
  };

  it('bounces a local project with zero runs on a project-data tab', () => {
    expect(shouldBounceToEvaluate(base)).toBe(true);
  });

  it('never bounces a shared selection, even when hasCurrentProjectRuns is false', () => {
    // The regression this guards: selectedProjectInfo is looked up in the
    // LOCAL project list, so a shared project whose id collides with a local
    // one could read a misleading (local) runsCount of 0 while the shared
    // source has real data. There is no Evaluate flow for shared projects at
    // all, so source must gate independent of hasCurrentProjectRuns.
    expect(shouldBounceToEvaluate({ ...base, selectedSource: 'shared' })).toBe(false);
  });

  it('does not bounce before projects have loaded', () => {
    expect(shouldBounceToEvaluate({ ...base, projectsLoaded: false })).toBe(false);
  });

  it('does not bounce when there are no projects', () => {
    expect(shouldBounceToEvaluate({ ...base, projectsCount: 0 })).toBe(false);
  });

  it('does not bounce while selectedProjectInfo has not resolved yet', () => {
    expect(shouldBounceToEvaluate({ ...base, selectedProjectInfo: null })).toBe(false);
  });

  it('does not bounce on a tab that is not overview/violations/map/history', () => {
    expect(shouldBounceToEvaluate({ ...base, activeTab: 'settings' })).toBe(false);
  });

  it('does not bounce once the project already has runs', () => {
    expect(shouldBounceToEvaluate({ ...base, hasCurrentProjectRuns: true })).toBe(false);
  });
});

describe('ROUTE_RENDERERS onDismiss source gating', () => {
  function baseProps(selectedSource) {
    return {
      navigation: { selectedProject: 'proj1', selectedRun: 'latest', selectedSource, projects: [] },
      dismissFinding: vi.fn(),
      applyDelta: vi.fn(),
      refreshDashboard: vi.fn(),
      bumpDismissRefresh: vi.fn(),
    };
  }

  it('file route wires up onDismiss for a local project', () => {
    const el = ROUTE_RENDERERS.file({ file: { path: 'a.py' }, runId: 'r1' }, baseProps('local'));
    expect(typeof el.props.onDismiss).toBe('function');
  });

  it('file route passes onDismiss as undefined for a shared project', () => {
    const el = ROUTE_RENDERERS.file({ file: { path: 'a.py' }, runId: 'r1' }, baseProps('shared'));
    expect(el.props.onDismiss).toBeUndefined();
  });

  it('finding route wires up onDismiss for a local project', () => {
    const el = ROUTE_RENDERERS.finding({ finding: {}, principle: 'P', dimension: 'Security' }, baseProps('local'));
    expect(typeof el.props.onDismiss).toBe('function');
  });

  it('finding route passes onDismiss as undefined for a shared project', () => {
    const el = ROUTE_RENDERERS.finding({ finding: {}, principle: 'P', dimension: 'Security' }, baseProps('shared'));
    expect(el.props.onDismiss).toBeUndefined();
  });

  it('evalprinciple route wires up onDismiss for a local project', () => {
    const el = ROUTE_RENDERERS.evalprinciple({ evalPrincipal: { principle: 'P', dimension: 'Security' } }, baseProps('local'));
    expect(typeof el.props.onDismiss).toBe('function');
  });

  it('evalprinciple route passes onDismiss as undefined for a shared project', () => {
    const el = ROUTE_RENDERERS.evalprinciple({ evalPrincipal: { principle: 'P', dimension: 'Security' } }, baseProps('shared'));
    expect(el.props.onDismiss).toBeUndefined();
  });

  it('eval-principle-detail (alias route) also gates onDismiss for a shared project', () => {
    const el = ROUTE_RENDERERS['eval-principle-detail']({ evalPrincipal: { principle: 'P', dimension: 'Security' } }, baseProps('shared'));
    expect(el.props.onDismiss).toBeUndefined();
  });
});

describe('Assistant drawer close on shared project switch', () => {
  // Task 19: shared projects have no mutation routes (dismiss/verify are
  // local-only). The drawer must close when switching to shared to prevent
  // writes to the local store under a shared project's id. The effect in
  // App.jsx guards both drawer close AND session re-bind on selectedSource.
  it('isSharedSource returns true for shared selections', () => {
    expect(isSharedSource('shared')).toBe(true);
  });

  it('isSharedSource returns false for local selections', () => {
    expect(isSharedSource('local')).toBe(false);
  });
});

// Final whole-branch review, Critical 1 (belt-and-braces): there is no
// Evaluate flow for shared projects. shouldShowEvaluateButton already keeps
// the TopBar from linking here, but a stale nav-stack entry could still land
// the router on the 'evaluate' route with a shared selection -- it must fall
// back to the Overview rather than rendering the dead-end evaluate screen.
describe('evaluate route: shared-source fallback (Critical 1 belt-and-braces)', () => {
  function baseProps(selectedSource) {
    const projects = [{ id: 'proj1', name: 'proj1' }];
    return {
      navigation: {
        selectedProject: 'proj1', selectedSource, projects,
        handleNavigate: vi.fn(), handleRunSelect: vi.fn(), loadProjects: vi.fn(),
      },
      dashboardData: { selectedProject: 'proj1', selectedSource, projects, projectsLoaded: true },
      serverHealth: { connected: true, setConnected: vi.fn() },
      evaluation: {},
    };
  }

  it('renders the Evaluate screen for a local selection', () => {
    const el = ROUTE_RENDERERS.evaluate({}, baseProps('local'));
    // EvaluateCase's own prop shape -- distinct from what the overview route renders.
    expect(el.props).toHaveProperty('onGoToProjects');
    expect(el.props).toHaveProperty('selectedProject', 'proj1');
  });

  it('falls back to exactly what the overview route renders for a shared selection', () => {
    const props = baseProps('shared');
    const evalEl = ROUTE_RENDERERS.evaluate({}, props);
    const overviewEl = ROUTE_RENDERERS.overview({}, props);
    expect(evalEl.type).toBe(overviewEl.type);
    expect(evalEl.props).not.toHaveProperty('onGoToProjects');
  });
});

// Important 3: the onboarding wizard must not auto-open over a teammate's
// working shared-project view just because state.projects (the LOCAL list)
// is empty.
describe('shouldAutoOpenOnboardingWizard', () => {
  const base = { projectsLoaded: true, projectsCount: 0, selectedSource: 'local', isEvaluating: false };

  it('opens for a fresh local install (no projects, local source, not evaluating)', () => {
    expect(shouldAutoOpenOnboardingWizard(base)).toBe(true);
  });

  it('does not open for a shared selection even with zero local projects', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, selectedSource: 'shared' })).toBe(false);
  });

  it('does not open before projects have loaded', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, projectsLoaded: false })).toBe(false);
  });

  it('does not open once local projects exist', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, projectsCount: 3 })).toBe(false);
  });

  it('does not open while an evaluation is running', () => {
    expect(shouldAutoOpenOnboardingWizard({ ...base, isEvaluating: true })).toBe(false);
  });
});

// Important 4: disconnecting the shared repo in Settings must not strand a
// 'shared' selection pointing at a config that no longer exists.
describe('resolveSelectionAfterSharedDisconnect', () => {
  it('does nothing when the current selection is not shared', () => {
    expect(resolveSelectionAfterSharedDisconnect({ selectedSource: 'local', projects: [{ id: 'p1' }] })).toBeNull();
  });

  it('resets to the first local project when one exists', () => {
    const projects = [{ id: 'p1', name: 'p1' }, { id: 'p2', name: 'p2' }];
    expect(resolveSelectionAfterSharedDisconnect({ selectedSource: 'shared', projects }))
      .toEqual({ id: 'p1', source: 'local' });
  });

  it('clears the selection to the app\'s no-project state when there are no local projects', () => {
    expect(resolveSelectionAfterSharedDisconnect({ selectedSource: 'shared', projects: [] }))
      .toEqual({ id: '', source: 'local' });
  });
});
