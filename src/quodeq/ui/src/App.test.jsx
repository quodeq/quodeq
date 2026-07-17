import { describe, expect, it, vi } from 'vitest';
import { buildEvalPrincipal, ROUTE_RENDERERS, isSharedSource, shouldBounceToEvaluate, shouldShowEvaluateButton } from './App.jsx';

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
