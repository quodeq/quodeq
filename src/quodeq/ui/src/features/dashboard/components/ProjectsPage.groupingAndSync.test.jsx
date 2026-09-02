import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import ProjectsPage from './ProjectsPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

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
      <ApiProvider value={fakeApi}>{ui}</ApiProvider>
    </QC>
  );
}


// Split from ProjectsPage.test.jsx: group-aware filtering (parent/
// subproject), published-age on originUrl-matched cards, the
// SyncedIndicator states, and the pending grade chip.

// Review findings 3 & 4 (final whole-branch review): group-aware query
// filtering for parent/subproject entries, and the empty-CTA filter trap.
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
    expect(screen.queryByText('Add your first project')).not.toBeInTheDocument();
    // The toolbar (search input included) must stay mounted so the filter
    // that caused this can actually be cleared.
    expect(screen.getByLabelText('filter projects by name')).toBeInTheDocument();
  });
});

// Review finding 7 (final whole-branch review): the "published <age>"
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
          latestDate: '2026-07-19T00:00:00Z',
        }]}
        actions={{}}
      />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText(/published /)).toBeInTheDocument());
  });
});

// Review finding 8 (final whole-branch review): SyncedIndicator wording and
// visibility.
describe('ProjectsPage — SyncedIndicator: "not synced yet" and unconfigured hiding', () => {
  it('shows "not synced yet" (never "just now") when nothing has synced', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
    });
    renderWithApi(<ProjectsPage projects={[{ id: 'a', name: 'app' }]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('not synced yet')).toBeInTheDocument());
    expect(screen.queryByText(/just now/)).not.toBeInTheDocument();
  });

  // Audit A2: a list that never loads used to render "not synced yet" with
  // no error and no working recovery control. It now renders a distinct
  // error state, and the same button that used to just say "refresh" is
  // the retry affordance -- clicking it calls the refresh endpoint (which
  // useSharedProjects' refresh() also uses to re-check status, see that
  // hook's own tests).
  it('shows "sync failed · retry" (no em-dash) when the shared list fails to load, and the button retries via refreshShared()', async () => {
    const refreshShared = vi.fn(async () => ({ stale: false, lastSynced: '2026-07-19T00:00:00Z' }));
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      sharedListProjects: vi.fn(async () => { throw new Error('list failed'); }),
      refreshShared,
    });
    const user = userEvent.setup();
    renderWithApi(<ProjectsPage projects={[{ id: 'a', name: 'app' }]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('sync failed · retry')).toBeInTheDocument());
    expect(screen.getByText('sync failed · retry').textContent).not.toMatch(/—/);
    expect(screen.queryByText('not synced yet')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'refresh' }));

    await waitFor(() => expect(refreshShared).toHaveBeenCalled());
  });

  it('hides the sync indicator and its refresh button entirely when no shared repo is configured', async () => {
    const fakeApi = makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    });
    renderWithApi(<ProjectsPage projects={[{ id: 'a', name: 'app' }]} actions={{}} />, fakeApi);

    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'refresh' })).not.toBeInTheDocument();
    expect(screen.queryByText(/synced|not synced yet|syncing/)).not.toBeInTheDocument();
  });
});

// Task 7: pending grade chip while a project summary is computing.
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

  it('shows the real grade, not the placeholder, once the summary settles', async () => {
    const projects = [{ id: 'a', name: 'proj-a', location: 'local', summaryPending: false, latestGrade: 'B', latestScore: 7.5 }];
    const fakeApi = makeFakeApi();
    const { container } = renderWithApi(<ProjectsPage projects={projects} actions={{}} />, fakeApi);
    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(container.querySelector('.projects-grade--pending')).toBeNull();
    expect(container.querySelector('.projects-grade')).toBeTruthy();
  });
});
