import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
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
    expect(screen.getByText('no completed evaluation in this shared project yet')).toBeInTheDocument();
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

describe('MapPage — shared read-only chip (Finding 6)', () => {
  const DIMS = [{ dimension: 'security', violations: [], compliance: [] }];

  it('shows the chip for a shared project with data', () => {
    renderPage(baseData({ accumulated: { dimensions: DIMS } }));
    expect(screen.getByText('shared · read-only')).toBeInTheDocument();
  });

  it('omits the chip for a local project', () => {
    renderPage(baseData({ selectedSource: 'local', selectedProject: 'p1', accumulated: { dimensions: DIMS } }));
    expect(screen.queryByText('shared · read-only')).toBeNull();
  });
});
