import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
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
