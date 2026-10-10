import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ProjectsPage from './ProjectsPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// One merged local+shared list, no tabs. The local list renders
// unconditionally; the shared list layers in once useSharedProjects resolves
// (cached-first, see that hook's own tests), so every render touches the API
// -- an ApiProvider is required from here on regardless of project count.
function makeFakeApi(overrides = {}) {
  const api = {
    getSharedStatus: vi.fn(async () => ({ configured: true, url: null, publish: { state: 'idle' } })),
    sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
    connectShared: vi.fn(async (url) => ({ configured: true, url })),
    startRefresh: vi.fn(async () => ({ started: true })),
    startPull: vi.fn(async (id) => ({ started: true, project: id })),
    publishProject: vi.fn(async () => ({ started: true })),
    ...overrides,
  };
  // The status poll reads getSyncStatus; these tests drive it through getSharedStatus.
  return { getSyncStatus: (...a) => api.getSharedStatus(...a), ...api };
}

function renderWithApi(ui, fakeApi) {
  const QC = withQueryClient();
  return render(
    <QC>
      <ApiProvider value={fakeApi}>
        <SidePaneProvider>{ui}</SidePaneProvider>
      </ApiProvider>
    </QC>
  );
}


// Split from ProjectsPage.test.jsx: group-aware filtering (parent/
// subproject), published-age on originUrl-matched cards, the sync strip
// states as the page renders them, and the pending grade chip. The header
// actions, connect card and pull state live in ProjectsPage.teamResults.test.jsx.

// Group-aware query filtering for parent/subproject entries, and the
// empty-CTA filter trap.
describe('ProjectsPage — group-aware filtering and the empty-filter trap', () => {
  const subprojectLocals = [
    { id: 'root-1', name: 'monorepo', latestDate: '2026-07-19T00:00:00Z' },
    { id: 'child-1', name: 'child-widget', parent: 'root-1', latestDate: '2026-07-18T00:00:00Z' },
  ];

  function configuredNoSharedApi(overrides = {}) {
    return makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: '2026-07-17T00:00:00Z', stale: false })),
      ...overrides,
    });
  }

  it('a query matching only a subproject keeps the whole parent/child group visible (no false-negative "no matches")', async () => {
    const fakeApi = configuredNoSharedApi();
    renderWithApi(
      <ProjectsPage
        projects={subprojectLocals}
        filters={{ query: 'widget', location: 'all', sort: 'activity' }}
        actions={{}}
      />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText('monorepo')).toBeInTheDocument());
    expect(screen.getByText('child-widget')).toBeInTheDocument();
    expect(screen.queryByText('no projects match your filters.')).not.toBeInTheDocument();
  });

  it('a query matching only the parent leaves the child with its own chips/action intact', async () => {
    const fakeApi = configuredNoSharedApi();
    renderWithApi(
      <ProjectsPage
        projects={subprojectLocals}
        filters={{ query: 'monorepo', location: 'all', sort: 'activity' }}
        actions={{}}
      />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText('monorepo')).toBeInTheDocument());
    expect(screen.getByText('child-widget')).toBeInTheDocument();
    // Both the parent's and the child's own publish button must still be
    // present -- before the fix, the child's entry (and its action) was
    // built from the post-filter list and vanished the moment the query
    // excluded the child's own name.
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'publish' })).toHaveLength(2));
  });

  it('filtering everything out keeps the toolbar mounted and shows a no-match line, not the empty-CTA', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      sharedListProjects: vi.fn(async () => ({
        projects: [{ id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z' }],
        lastSynced: '2026-07-17T00:00:00Z',
        stale: false,
      })),
    });
    renderWithApi(
      <ProjectsPage
        projects={[]}
        filters={{ query: 'nomatch', location: 'all', sort: 'activity' }}
        actions={{}}
      />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText('no projects match your filters.')).toBeInTheDocument());
    expect(screen.queryByText('An evaluations repository')).not.toBeInTheDocument();
    // The toolbar (search input included) must stay mounted so the filter
    // that caused this can actually be cleared.
    expect(screen.getByLabelText('filter projects by name')).toBeInTheDocument();
  });
});

// The "published <age>"
// decoration must also work for shared matches found by originUrl, not just
// by id (usePublish's own publishedAtByProject is keyed by the SHARED
// entry's id, which an originUrl match never shares with the local id).
describe('ProjectsPage — published-age on originUrl-matched cards', () => {
  it('shows "published <time>" for a local card matched to a shared entry with a different id via originUrl', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      sharedListProjects: vi.fn(async () => ({
        projects: [{
          id: 'remote-9',
          name: 'app',
          originUrl: 'https://github.com/org/app.git',
          publishedAt: '2026-07-10T00:00:00Z',
        }],
        lastSynced: '2026-07-17T00:00:00Z',
        stale: false,
      })),
    });
    renderWithApi(
      <ProjectsPage
        projects={[{
          id: 'local-1',
          name: 'app',
          originUrl: 'https://github.com/org/app',
          // Evaluated before the publish, so the server copy is current, not behind.
          latestDate: '2026-07-01T00:00:00Z',
        }]}
        actions={{}}
      />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText(/published /)).toBeInTheDocument());
  });
});

// The sync strip under the header replaced the toolbar's SyncedIndicator:
// its wording and visibility from the page's point of view.
describe('ProjectsPage — sync strip: "not synced yet", load failure and unconfigured hiding', () => {
  it('shows "not synced yet" (never "just now") when nothing has synced, and no toolbar refresh button', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
    });
    renderWithApi(<ProjectsPage projects={[{ id: 'a', name: 'app' }]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('0 projects · not synced yet')).toBeInTheDocument());
    expect(screen.queryByText(/just now/)).not.toBeInTheDocument();
    expect(screen.getByText('github.com/team/results')).toBeInTheDocument();
    // The strip replaced the toolbar indicator: no ⟳ "refresh" button is left in the toolbar.
    expect(screen.queryByRole('button', { name: 'refresh' })).not.toBeInTheDocument();
  });

  // A list that never loads renders a distinct failure, never "not synced
  // yet", and its retry starts a refresh (useSharedProjects' refresh() also
  // re-checks the status, see that hook's own tests).
  it('shows a load failure with a retry (no em-dash) when the shared list fails to load, and retry calls startRefresh()', async () => {
    const startRefresh = vi.fn(async () => ({ started: true }));
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      sharedListProjects: vi.fn(async () => { throw new Error('list failed'); }),
      startRefresh,
    });
    const user = userEvent.setup();
    renderWithApi(<ProjectsPage projects={[{ id: 'a', name: 'app' }]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText(/could not read the evaluations repository/)).toBeInTheDocument());
    expect(screen.getByText(/could not read the evaluations repository/).textContent).not.toMatch(/—/);
    expect(screen.queryByText(/not synced yet/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'retry' }));

    await waitFor(() => expect(startRefresh).toHaveBeenCalled());
  });

  it('hides the strip entirely when no shared repo is configured', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    });
    renderWithApi(<ProjectsPage projects={[{ id: 'a', name: 'app' }]} actions={{}} />, fakeApi);

    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /update|refresh/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/synced|not synced yet|syncing/)).not.toBeInTheDocument();
  });
});

// Pending grade chip while a project summary is computing.
describe('ProjectsPage — pending grade chip', () => {
  it('shows a pending placeholder chip while the summary is computing', async () => {
    const projects = [{ id: 'a', name: 'proj-a', location: 'local', summaryPending: true }];
    const fakeApi = makeFakeApi();
    const { container } = renderWithApi(<ProjectsPage projects={projects} actions={{}} />, fakeApi);
    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    const chip = container.querySelector('.projects-grade--pending');
    expect(chip).toBeTruthy();
    expect(chip).toHaveAttribute('aria-label');
  });

  it('shows the last known grade dimmed while the summary is recomputed', async () => {
    const projects = [{ id: 'a', name: 'proj-a', location: 'local', summaryPending: true, latestGrade: 'B', latestScore: 7.4 }];
    const fakeApi = makeFakeApi();
    const { container } = renderWithApi(<ProjectsPage projects={projects} actions={{}} />, fakeApi);
    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(container.querySelector('.projects-grade--pending')).toBeNull();
    const chip = container.querySelector('.projects-grade--updating');
    expect(chip).toHaveTextContent('7.4 B');
    expect(chip).toHaveAttribute('aria-busy', 'true');
  });

  it('shows the real grade, not the placeholder, once the summary settles', async () => {
    const projects = [{ id: 'a', name: 'proj-a', location: 'local', summaryPending: false, latestGrade: 'B', latestScore: 7.5 }];
    const fakeApi = makeFakeApi();
    const { container } = renderWithApi(<ProjectsPage projects={projects} actions={{}} />, fakeApi);
    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(container.querySelector('.projects-grade--pending')).toBeNull();
    expect(container.querySelector('.projects-grade')).toBeTruthy();
  });
});
