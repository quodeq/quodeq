import { render, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardPage, { selectDashboardProjectInfo } from './DashboardPage.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// Split from DashboardPage.test.jsx: runMode's own loading gate, the
// shared-selection/zero-local-projects teammate persona, and frame
// stability across the empty branches.

// Scenario 2 (collision): runMode renders RunOverviewPanel, which has its own
// inline loading state (`!dashboard.dimensions`). Before the page's own
// isLoading/DashboardContent-mount decision accounted for that, the page-level
// grace loader and RunOverviewPanel's inline spinner could both mount at once.
describe('DashboardPage runMode loading gate', () => {
  const runModeLoading = {
    projectsLoaded: true,
    projects: [{ id: 'p1', name: 'p1' }],
    selectedProject: 'p1',
    selectedRun: 'r1',
    dashboard: null,
    accumulated: null,
    loading: true,
    isFetching: false,
    error: null,
    availableRuns: [{ runId: 'r1', status: 'complete' }],
  };

  it('renders exactly one LoadingScreen before the run payload has resolved', () => {
    const { container } = render(
      <SidePaneProvider>
        <DashboardPage data={runModeLoading} callbacks={{}} runMode={true} />
      </SidePaneProvider>,
    );
    expect(container.querySelectorAll('.loading-screen').length).toBe(1);
    expect(container.querySelector('.loading-screen').className).toContain('loading-screen--inline');
  });

  it('renders exactly one LoadingScreen once the run payload resolves without dimensions yet', () => {
    const { container } = render(
      <SidePaneProvider>
        <DashboardPage
          data={{
            ...runModeLoading,
            dashboard: { selectedRun: { runId: 'r1', dateLabel: '2026-05-01' }, trend: [] },
          }}
          callbacks={{}}
          runMode={true}
        />
      </SidePaneProvider>,
    );
    expect(container.querySelectorAll('.loading-screen').length).toBe(1);
  });
});

// Teammate persona (shared-repo onboarding): a teammate with ZERO local
// projects selects a shared project. The local-list empty-state gate must not
// wall off the Overview when the selection is shared -- the shared data loads
// fine and its own loading/empty states take over. Same gate class already
// fixed on MapPage/HistoryPage/ViolationsPage.
describe('DashboardPage, teammate persona: shared selection + zero local projects', () => {
  const sharedNoLocalData = {
    projectsLoaded: true,
    projects: [],
    selectedProject: 'shared-1',
    selectedSource: 'shared',
    sharedProjectInfo: { id: 'shared-1', name: 'shared-1', displayName: 'Shared Repo' },
    dashboard: {
      dimensions: [],
      trend: [],
      selectedRun: { runId: 'r1', dateLabel: '2026-05-01' },
    },
    accumulated: { dimensions: [] },
    loading: false,
    isFetching: false,
    error: null,
    availableRuns: [{ runId: 'r1', status: 'failed' }],
  };

  it('shared source with an empty LOCAL projects list renders the shared content path, not the Add-a-project wall', () => {
    const { getByText, queryByText } = render(
      <DashboardPage data={sharedNoLocalData} callbacks={{}} runMode={false} />,
    );
    expect(queryByText('No projects yet')).toBeNull();
    expect(queryByText('Add a project')).toBeNull();
    expect(getByText('no completed evaluation in this remote project yet')).toBeTruthy();
  });

  it('local source with an empty local projects list still shows the Add-a-project wall (unchanged)', () => {
    const { getByText } = render(
      <DashboardPage
        data={{ ...sharedNoLocalData, selectedSource: 'local', selectedProject: '', sharedProjectInfo: null }}
        callbacks={{}}
        runMode={false}
      />,
    );
    expect(getByText('No projects yet')).toBeTruthy();
  });

  // Remote-content awareness: zero local projects + a shared repo with
  // published content must route to the repositories tab, not dead-end on
  // "Add a project" (spec 2026-07-23-remote-repos-without-local-projects).
  it('local source, zero local projects, shared content: offers Browse remote repositories', () => {
    const onNavigate = vi.fn();
    const { getByText, queryByText } = render(
      <DashboardPage
        data={{ ...sharedNoLocalData, selectedSource: 'local', selectedProject: '', sharedProjectInfo: null, sharedHasContent: true }}
        callbacks={{ onNavigate }}
        runMode={false}
      />,
    );
    expect(getByText('No local projects yet')).toBeTruthy();
    expect(queryByText('No projects yet')).toBeNull();
    fireEvent.click(getByText('Browse remote repositories'));
    expect(onNavigate).toHaveBeenCalledWith('projects');
  });

  it('local source, zero local projects, NO shared content: unchanged Add-a-project wall', () => {
    const { getByText } = render(
      <DashboardPage
        data={{ ...sharedNoLocalData, selectedSource: 'local', selectedProject: '', sharedProjectInfo: null, sharedHasContent: false }}
        callbacks={{}}
        runMode={false}
      />,
    );
    expect(getByText('No projects yet')).toBeTruthy();
    expect(getByText('Add a project')).toBeTruthy();
  });
});

// P4: the Overview's frame must stay mounted across every state, including
// the "no projects"/"no project selected" empty branches -- otherwise the
// page jumps (no .dashboard-page wrapper, then one appears) the moment real
// content shows up. The error and no-completed-evaluation branches already
// wrap in .dashboard-page; these bare EmptyState returns did not.
describe('DashboardPage frame stability in empty branches', () => {
  const zeroLocalProjectsData = {
    projectsLoaded: true,
    projects: [],
    selectedSource: 'local',
    selectedProject: '',
    sharedProjectInfo: null,
    dashboard: null,
    accumulated: { dimensions: [] },
    loading: false,
    isFetching: false,
    error: null,
    availableRuns: [],
  };

  it('wraps the no-local-projects (local source) empty state in .dashboard-page', () => {
    const { container, getByText } = render(
      <DashboardPage
        data={{ ...zeroLocalProjectsData, sharedHasContent: false }}
        callbacks={{}}
        runMode={false}
      />,
    );
    const page = container.querySelector('.dashboard-page');
    expect(page).toBeTruthy();
    expect(page.contains(getByText('No projects yet'))).toBe(true);
  });

  it('wraps the no-local-projects-but-shared-content empty state in .dashboard-page', () => {
    const { container, getByText } = render(
      <DashboardPage
        data={{ ...zeroLocalProjectsData, sharedHasContent: true }}
        callbacks={{}}
        runMode={false}
      />,
    );
    const page = container.querySelector('.dashboard-page');
    expect(page).toBeTruthy();
    expect(page.contains(getByText('No local projects yet'))).toBe(true);
  });

  it('wraps the no-project-selected empty state in .dashboard-page', () => {
    const { container, getByText } = render(
      <DashboardPage
        data={{ projectsLoaded: true, projects: [{ id: 'p1', name: 'p1' }], selectedProject: '', loading: false, isFetching: false, error: null, availableRuns: [] }}
        callbacks={{}}
        runMode={false}
      />,
    );
    const page = container.querySelector('.dashboard-page');
    expect(page).toBeTruthy();
    expect(page.contains(getByText('No project selected'))).toBe(true);
  });
});
