import { describe, it, expect, vi } from 'vitest';
import { ViolationsRoute, violationsLookupsFor, buildEvalPrincipal } from './violationsRoute.jsx';

function dims() {
  return [
    { dimension: 'security', fromRunId: 'run-1', principles: [{ name: 'P1', grade: 'B', score: '7.5' }] },
    { dimension: 'perf', fromRunId: 'run-2', principles: [{ principle: 'P2', grade: 'C' }] },
  ];
}

function routeProps(acc) {
  return {
    dashboardData: { latestAccumulated: acc, accumulated: null, selectedDisplayName: 'p1', loading: false, isFetching: false },
    navigation: { selectedProject: 'proj1', selectedSource: 'local', projects: [], projectsLoaded: true, handleNavigate: vi.fn(), navStackLength: 1 },
    dismissRefreshKey: 0,
    refreshDashboard: vi.fn(),
    scheduleDashboardReconcile: vi.fn(),
  };
}

describe('violationsLookupsFor', () => {
  it('returns the same maps while the dimensions array is the same reference', () => {
    const d = dims();
    const first = violationsLookupsFor(d);
    expect(violationsLookupsFor(d)).toBe(first);
    expect(first.dimMap.get('perf').fromRunId).toBe('run-2');
    expect(first.principleMap.get('security\0P1').grade).toBe('B');
    // Principles may carry `principle` instead of `name`.
    expect(first.principleMap.get('perf\0P2').grade).toBe('C');
  });

  it('rebuilds for a different array', () => {
    expect(violationsLookupsFor(dims())).not.toBe(violationsLookupsFor(dims()));
  });
});

describe('ViolationsRoute', () => {
  it('stays hook-free and threads fromRunId through onPrincipleClick across re-renders', () => {
    const props = routeProps({ dimensions: dims() });
    // Invoked twice with the same payload, as a parent state bump would; the
    // App tests rely on this being callable as a plain function.
    ViolationsRoute({ params: {}, props });
    const el = ViolationsRoute({ params: {}, props });
    el.props.callbacks.onPrincipleClick({ dimension: 'security', principle: 'P1' });
    expect(props.navigation.handleNavigate).toHaveBeenCalledWith('evalprinciple', expect.objectContaining({
      evalPrincipal: expect.objectContaining({ runId: 'run-1', grade: 'B' }),
    }));
  });

  it('renders with no accumulated payload', () => {
    const el = ViolationsRoute({ params: {}, props: routeProps(null) });
    expect(el.props.data.accumulatedDimensions).toEqual([]);
  });

  it('onTypeClick opens the file page on the type\'s own findings with the dimension\'s run', () => {
    const d = dims();
    d[0].violations = [{ req: 'S-1', file: 'a.py', line: 1, severity: 'minor' }, { req: 'S-1', file: 'b.py', line: 2, severity: 'major' }, { req: 'S-2', file: 'c.py', line: 3, severity: 'minor' }];
    const props = routeProps({ dimensions: d });
    const el = ViolationsRoute({ params: {}, props });
    el.props.callbacks.onTypeClick({ req: 'S-1', text: 'Hash it', dimension: 'security', runId: 'run-1', dateLabel: '26 Sep', violations: d[0].violations.slice(0, 2) });
    expect(props.navigation.handleNavigate).toHaveBeenCalledWith('file', expect.objectContaining({
      file: expect.objectContaining({ file: 'S-1 · Hash it', total: 2 }),
      runId: 'run-1', dateLabel: '26 Sep', sourceTab: 'violations',
    }));
  });
});

describe('buildEvalPrincipal', () => {
  it('keeps a genuine score of 0, not coercing it to null', () => {
    const result = buildEvalPrincipal({ principle: 'P1', dimension: 'security' }, { score: 0, grade: 'F' }, 'run-1');
    expect(result.score).toBe(0);
  });
});
