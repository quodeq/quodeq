import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useState } from 'react';
import MapPage from './MapPage.jsx';

// Final whole-branch review: Critical 1 (evaluate CTA gating for shared
// projects) and Finding 6 (shared read-only chip). MapPage previously never
// received selectedSource at all (App.jsx's `map` renderer didn't thread
// it), so the "Start evaluation" CTA in the no-evaluations-yet empty state
// always rendered even for a shared project.
function baseData(overrides = {}) {
  return {
    accumulated: null,
    dashboard: null,
    projectName: 'Shared Repo',
    projects: [{ id: 'p1', name: 'p1' }],
    projectsLoaded: true,
    selectedProject: 'shared-1',
    selectedSource: 'shared',
    loading: false,
    isFetching: false,
    ...overrides,
  };
}

function renderPage(data, callbacks = {}) {
  return render(<MapPage data={data} callbacks={callbacks} />);
}

describe('MapPage — evaluate CTA gating for shared (Critical 1)', () => {
  it('shared source, no evaluations yet: no Start evaluation CTA, shared-specific copy', () => {
    renderPage(baseData());
    expect(screen.getByText('No completed evaluation yet')).toBeInTheDocument();
    expect(screen.getByText('no completed evaluation in this remote project yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Start evaluation' })).toBeNull();
  });

  it('local source, no evaluations yet: Start evaluation CTA present (existing behavior)', () => {
    renderPage(baseData({ selectedSource: 'local', selectedProject: 'p1' }));
    expect(screen.getByRole('button', { name: 'Start evaluation' })).toBeInTheDocument();
  });
});

describe('MapPage, teammate persona: shared selection + zero local projects', () => {
  it('shared source with an empty LOCAL projects list renders the shared content path, not the Add-a-project wall', () => {
    renderPage(baseData({ projects: [] }));
    expect(screen.queryByText('No projects yet')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a project' })).toBeNull();
  });

  it('local source with an empty local projects list still shows the Add-a-project wall (unchanged)', () => {
    renderPage(baseData({ selectedSource: 'local', selectedProject: '', projects: [] }));
    expect(screen.getByText('No projects yet')).toBeInTheDocument();
  });
});

describe('MapPage — scenario 9: loader gate, containment, refresh dim', () => {
  it('background refetch over an empty project keeps the empty state, no loader', () => {
    const { container } = renderPage(baseData({ loading: false, isFetching: true }));
    expect(container.querySelector('.loading-screen')).toBeNull();
    expect(screen.getByText('No completed evaluation yet')).toBeInTheDocument();
  });

  it('initial load renders exactly one inline loader inside the page frame', () => {
    const { container } = renderPage(baseData({ loading: true, isFetching: true }));
    expect(container.querySelectorAll('.loading-screen').length).toBe(1);
    const loader = container.querySelector('.loading-screen--inline');
    expect(loader).not.toBeNull();
    const frame = container.querySelector('.map-page--terminal');
    expect(frame).not.toBeNull();
    expect(frame.contains(loader)).toBe(true);
  });

  it('applies the refresh dim class to the empty state during a background refetch', () => {
    const { container } = renderPage(baseData({ loading: false, isFetching: true }));
    expect(container.querySelector('.map-page--terminal').className).toContain('dashboard-refreshing');
  });

  it('applies the refresh dim class to real content during a background refetch', () => {
    const DIMS = [{ dimension: 'security', violations: [], compliance: [] }];
    const { container } = renderPage(baseData({
      accumulated: { dimensions: DIMS }, loading: false, isFetching: true,
    }));
    expect(container.querySelector('.map-page--terminal').className).toContain('dashboard-refreshing');
  });
});

describe('MapPage — error state + retry feedback (P4-T2)', () => {
  it('error + no data renders the framed error state with a working Retry', () => {
    const onRetry = vi.fn();
    renderPage(
      baseData({ selectedSource: 'local', selectedProject: 'p1', error: 'Failed to load' }),
      { onRetry },
    );
    expect(screen.getByText("Couldn't load this project")).toBeInTheDocument();
    fireEvent.click(screen.getByText('Retry'));
    expect(onRetry).toHaveBeenCalled();
  });

  it('error + isFetching renders the inline loader instead of the error state', () => {
    const { container } = renderPage(
      baseData({ selectedSource: 'local', selectedProject: 'p1', error: 'Failed to load', isFetching: true }),
    );
    expect(screen.queryByText("Couldn't load this project")).toBeNull();
    expect(container.querySelector('.loading-screen')).toBeTruthy();
  });

  it('data present with a stale error still renders the data, not the error screen', () => {
    const DIMS = [{ dimension: 'security', violations: [], compliance: [] }];
    renderPage(baseData({
      selectedSource: 'local', selectedProject: 'p1',
      accumulated: { dimensions: DIMS },
      error: 'Failed to load',
    }));
    expect(screen.queryByText("Couldn't load this project")).toBeNull();
  });
});

/* Mimics the App wiring (see ROUTE_RENDERERS.map): path/vizStyle/viewMode/
   galaxyMode are route params — drilling into a folder pushes a nav-stack
   entry, navigating up to a path already in the trail unwinds to it, and
   mode/style toggles replace in place. The harness keeps a tiny stack plus
   an action log so the push/replace/unwind contract is exercised, not just
   that the view flipped. */
function NavHarness({ data, log }) {
  const [stack, setStack] = useState([{}]);
  const top = stack[stack.length - 1];
  const replaceTop = (patch) => setStack((s) => s.slice(0, -1).concat([{ ...s[s.length - 1], ...patch }]));
  const nav = {
    path: top.path || '',
    vizStyle: top.vizStyle,
    viewMode: top.viewMode,
    galaxyMode: top.galaxyMode,
    onPathChange: (path) => setStack((s) => {
      for (let i = s.length - 2; i >= 0; i--) {
        if ((s[i].path || '') === path) { log.push(['goTo', i]); return s.slice(0, i + 1); }
      }
      log.push(['push', path]);
      return s.concat([{ ...s[s.length - 1], path }]);
    }),
    onVizStyleChange: (v) => { log.push(['replace', 'vizStyle', v]); replaceTop({ vizStyle: v }); },
    onViewModeChange: (v) => { log.push(['replace', 'viewMode', v]); replaceTop({ viewMode: v }); },
    onGalaxyModeChange: (v) => { log.push(['replace', 'galaxyMode', v]); replaceTop({ galaxyMode: v }); },
  };
  return <MapPage data={data} callbacks={{}} nav={nav} />;
}

describe('MapPage — drill-down and toggles live in the nav stack', () => {
  // Two top-level entries so collapseSingleChildren keeps `src` as a
  // distinct drillable folder.
  const DIMS = [{
    dimension: 'security',
    violations: [
      { file: 'src/a.py', severity: 'minor', principle: 'P1' },
      { file: 'src/b.py', severity: 'major', principle: 'P1' },
      { file: 'main.py', severity: 'minor', principle: 'P2' },
    ],
    compliance: [],
  }];
  const data = () => ({
    accumulated: { dimensions: DIMS },
    dashboard: null,
    projectName: 'proj',
    projects: [{ id: 'p1', name: 'p1' }],
    projectsLoaded: true,
    selectedProject: 'p1',
    selectedSource: 'local',
    loading: false,
    isFetching: false,
  });

  it('style toggle replaces, folder drill pushes, breadcrumb-up unwinds to the trail entry', () => {
    const log = [];
    const { container } = render(<NavHarness data={data()} log={log} />);

    // Switch to the risk-matrix style: a replace, not a push.
    fireEvent.click(screen.getByRole('button', { name: 'Risk Matrix' }));
    expect(log).toEqual([['replace', 'vizStyle', 'riskmatrix']]);

    // Drill into the `src` folder circle: a push.
    const circle = container.querySelector('circle[role="button"]');
    expect(circle).not.toBeNull();
    fireEvent.click(circle);
    expect(log[1]).toEqual(['push', 'src']);
    // The controlled path round-tripped: breadcrumb now shows the folder.
    expect(screen.getAllByText('src').length).toBeGreaterThan(0);

    // Breadcrumb back to the project root: unwinds to the earlier entry
    // (the browser-back equivalent), never a fresh push.
    fireEvent.click(screen.getByRole('button', { name: 'proj' }));
    expect(log[2]).toEqual(['goTo', 0]);
    // The unwound entry still carries the style set by the replace.
    expect(screen.getByRole('button', { name: 'Risk Matrix' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('view-mode toggle on the circle pack replaces in place', () => {
    const log = [];
    render(<NavHarness data={data()} log={log} />);
    fireEvent.click(screen.getByRole('button', { name: 'Violations' }));
    expect(log).toEqual([['replace', 'viewMode', 'violations']]);
    expect(screen.getByRole('button', { name: 'Violations' })).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('MapPage — shared read-only chip (Finding 6)', () => {
  const DIMS = [{ dimension: 'security', violations: [], compliance: [] }];

  it('shows the chip for a shared project with data', () => {
    renderPage(baseData({ accumulated: { dimensions: DIMS } }));
    expect(screen.getByText('remote · read-only')).toBeInTheDocument();
  });

  it('omits the chip for a local project', () => {
    renderPage(baseData({ selectedSource: 'local', selectedProject: 'p1', accumulated: { dimensions: DIMS } }));
    expect(screen.queryByText('remote · read-only')).toBeNull();
  });
});
