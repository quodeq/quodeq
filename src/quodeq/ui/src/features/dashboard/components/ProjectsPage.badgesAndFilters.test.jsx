import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import ProjectsPage from './ProjectsPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// Task 7: one merged local+shared list, no tabs. The local list renders
// unconditionally; the shared list layers in once useSharedProjects resolves
// (cached-first, see that hook's own tests), so every render touches the API
// -- an ApiProvider is required from here on regardless of project count.
function makeFakeApi(overrides = {}) {
  return {
    getSharedStatus: vi.fn(async () => ({ configured: true, url: null, publish: { state: 'idle' } })),
    sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
    connectShared: vi.fn(async (url) => ({ configured: true, url })),
    refreshShared: vi.fn(async () => ({ stale: false, lastSynced: '2026-07-17T00:00:00Z' })),
    pullSharedProject: vi.fn(async (id) => ({ imported: true, projectId: id })),
    publishProject: vi.fn(async () => ({ started: true })),
    ...overrides,
  };
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


// Split from ProjectsPage.test.jsx: setup-incomplete badges, the
// initial loading gate, and the merged local+shared list with its
// filter/sort toolbar.

describe('ProjectsPage', () => {
  it('renders a "setup incomplete" badge on online-location projects', async () => {
    const projects = [
      { id: 'a', name: 'local-one', location: 'local' },
      { id: 'b', name: 'online-legacy', location: 'online' },
    ];
    const fakeApi = makeFakeApi();
    renderWithApi(<ProjectsPage projects={projects} actions={{}} />, fakeApi);
    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    const badges = screen.queryAllByText(/setup incomplete/i);
    expect(badges).toHaveLength(1);
    expect(badges[0]).toHaveClass('badge', 'badge--tag', 'badge--warning');
  });

  it('renders no badge when all projects are local', async () => {
    const projects = [
      { id: 'a', name: 'one', location: 'local' },
      { id: 'b', name: 'two', location: 'local' },
    ];
    const fakeApi = makeFakeApi();
    renderWithApi(<ProjectsPage projects={projects} actions={{}} />, fakeApi);
    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(screen.queryByText(/setup incomplete/i)).not.toBeInTheDocument();
  });
});

// P4: ProjectsPage previously had no loading signal at all, so the empty
// local-projects array during the initial fetch rendered the "Add your first
// project" CTA -- a false-empty flash before the real list ever had a chance
// to arrive. `projectsLoaded` now gates that, mirroring the other pages'
// !projectsLoaded contract (frame stays, contained loader, no fullscreen).
describe('ProjectsPage — initial loading gate (P4)', () => {
  it('renders a contained loader inside the page frame while projectsLoaded is false, not the empty CTA', async () => {
    const fakeApi = makeFakeApi();
    const { container } = renderWithApi(
      <ProjectsPage projects={[]} projectsLoaded={false} actions={{}} />,
      fakeApi,
    );
    const frame = container.querySelector('.projects-page');
    expect(frame).toBeTruthy();
    const loader = frame.querySelector('.loading-screen--inline');
    expect(loader).toBeTruthy();
    expect(screen.queryByText('Add your first project')).not.toBeInTheDocument();
    // The header must not claim "0 repositories evaluated" while the real
    // count is still unknown -- match the "loading…" vocabulary used by
    // the other pages' TermHeader subs (Violations/Map/History).
    expect(screen.queryByText(/repositories evaluated/)).not.toBeInTheDocument();
    expect(screen.getByText('loading…')).toBeInTheDocument();
  });

  it('renders the empty CTA once projectsLoaded is true and there are still no projects', async () => {
    const fakeApi = makeFakeApi();
    const { container } = renderWithApi(<ProjectsPage projects={[]} projectsLoaded actions={{}} />, fakeApi);
    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(screen.getByText('Add your first project')).toBeInTheDocument();
    expect(container.querySelector('.loading-screen--inline')).not.toBeInTheDocument();
  });
});

// Task 7: tabs are gone. Local and shared projects render together in one
// list, filtered/sorted via a controlled toolbar (state lives in the nav
// stack, see actions.onFiltersChange).
describe('ProjectsPage — merged list, no tabs', () => {
  it('renders local and shared projects in one list without tabs', async () => {
    const fakeApi = makeFakeApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [
          { id: 'p-local', name: 'app', publishedAt: 1 },
          { id: 'p-cloud', name: 'lib', publishedAt: 2 },
        ],
        lastSynced: 1, stale: false,
      })),
    });
    renderWithApi(
      <ProjectsPage
        projects={[{ id: 'p-local', name: 'app', latestDate: '2026-07-19' }]}
        actions={{}}
      />,
      fakeApi,
    );
    expect(screen.queryByRole('tablist')).toBeNull();
    // a11y: the search input names itself for screen readers instead of
    // relying on the visible placeholder alone.
    expect(screen.getByLabelText('filter projects by name')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('app')).toBeInTheDocument();
      expect(screen.getByText('lib')).toBeInTheDocument();
    });
  });

  it('shows update for published-behind cards, publish for unpublished, pull for shared-only', async () => {
    const fakeApi = makeFakeApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [
          { id: 'p-behind', name: 'app', publishedAt: 1 },
          { id: 'p-cloud', name: 'lib', publishedAt: 2 },
        ],
        lastSynced: 1, stale: false,
      })),
    });
    renderWithApi(
      <ProjectsPage
        projects={[
          { id: 'p-behind', name: 'app', latestDate: '2026-07-19' },
          { id: 'p-new', name: 'tool', latestDate: '2026-07-18' },
        ]}
        actions={{}}
      />,
      fakeApi,
    );
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'update' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'publish' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'pull local copy' })).toBeInTheDocument();
    });
  });

  it('filters by location via the dropdown pill', async () => {
    const fakeApi = makeFakeApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [{ id: 'p-cloud', name: 'lib', publishedAt: 2 }],
        lastSynced: 1, stale: false,
      })),
    });
    const onFiltersChange = vi.fn();
    renderWithApi(
      <ProjectsPage
        projects={[{ id: 'p-local', name: 'app', latestDate: '2026-07-19' }]}
        actions={{ onFiltersChange }}
      />,
      fakeApi,
    );
    await waitFor(() => expect(screen.getByText('lib')).toBeInTheDocument());
    // Pills are controlled by the `filters` prop: picking a menu option
    // emits onFiltersChange; the menu closes after the pick.
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /location: all/ }));
    await user.click(screen.getByRole('menuitemradio', { name: 'local' }));
    expect(onFiltersChange).toHaveBeenCalledWith({ query: '', location: 'local', sort: 'activity' });
    expect(screen.queryByRole('menuitemradio', { name: 'local' })).toBeNull();
  });

  it('changes sort via the dropdown pill', async () => {
    const onFiltersChange = vi.fn();
    renderWithApi(
      <ProjectsPage
        projects={[{ id: 'p-local', name: 'app', latestDate: '2026-07-19' }]}
        actions={{ onFiltersChange }}
      />,
      makeFakeApi(),
    );
    await waitFor(() => expect(screen.getByText('app')).toBeInTheDocument());
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /sort: recent activity/ }));
    await user.click(screen.getByRole('menuitemradio', { name: 'score' }));
    expect(onFiltersChange).toHaveBeenCalledWith({ query: '', location: 'all', sort: 'score' });
  });

  it('hides provenance badges and the location pill when no shared repo is configured', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    });
    renderWithApi(
      <ProjectsPage projects={[{ id: 'a', name: 'solo', latestDate: '2026-07-19' }]} actions={{}} />,
      fakeApi,
    );
    await waitFor(() => expect(screen.getByText('solo')).toBeInTheDocument());
    // Without a shared repo every card would read LOCAL -- pure noise.
    expect(screen.queryByText('LOCAL')).toBeNull();
    expect(screen.queryByRole('button', { name: /location:/ })).toBeNull();
    // Search and sort remain.
    expect(screen.getByLabelText('filter projects by name')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sort:/ })).toBeInTheDocument();
  });

  it('ignores a stale location filter when no shared repo is configured', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    });
    renderWithApi(
      <ProjectsPage
        projects={[{ id: 'a', name: 'solo', latestDate: '2026-07-19' }]}
        filters={{ query: '', location: 'shared', sort: 'activity' }}
        actions={{}}
      />,
      fakeApi,
    );
    // A leftover location=shared from before disconnecting must not blank
    // the page now that the pill to clear it is hidden.
    await waitFor(() => expect(screen.getByText('solo')).toBeInTheDocument());
  });

  it('shows LOCAL / PUBLISHED / REMOTE state badges on the cards', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://x/r.git', publish: { state: 'idle' } })),
      sharedListProjects: vi.fn(async () => ({
        projects: [
          { id: 'p-both', name: 'app', publishedAt: 2 },
          { id: 'p-cloud', name: 'lib', publishedAt: 3 },
        ],
        lastSynced: 1, stale: false,
      })),
    });
    renderWithApi(
      <ProjectsPage
        projects={[
          { id: 'p-both', name: 'app', latestDate: '2026-07-19' },
          { id: 'p-solo', name: 'tool', latestDate: '2026-07-18' },
        ]}
        actions={{}}
      />,
      fakeApi,
    );
    await waitFor(() => {
      expect(screen.getByText('PUBLISHED')).toBeInTheDocument();
      expect(screen.getByText('LOCAL')).toBeInTheDocument();
      expect(screen.getByText('REMOTE')).toBeInTheDocument();
    });
    expect(screen.getByText('LOCAL')).toHaveClass('badge', 'badge--pill', 'badge--neutral');
    expect(screen.getByText('PUBLISHED')).toHaveClass('badge--success');
    expect(screen.getByText('REMOTE')).toHaveClass('badge--info');
  });
});
