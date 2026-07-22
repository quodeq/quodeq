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

describe('ProjectsPage — shared entries (configured)', () => {
  function configuredApi(overrides = {}) {
    return makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git' })),
      sharedListProjects: vi.fn(async () => ({
        projects: [
          { id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z', runsCount: 3 },
        ],
        lastSynced: '2026-07-17T00:00:00Z',
        stale: false,
      })),
      ...overrides,
    });
  }

  it('renders shared-only cards with "published by"', async () => {
    const fakeApi = configuredApi();
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    expect(screen.getByText(/published by ana/)).toBeInTheDocument();
  });

  // Regression: the header actions used to be gated on `projects.length > 0`,
  // so a user with zero local projects but a shared-only project had no way
  // to add or import from this page (allEntries is non-empty here, so the
  // EmptyProjectsCTA doesn't render either). Gate on `isEmpty` instead.
  it('shows the add/import header buttons with zero local projects but a shared project present', async () => {
    const onAddProject = vi.fn();
    const onImportProject = vi.fn();
    const fakeApi = configuredApi();
    renderWithApi(
      <ProjectsPage projects={[]} actions={{ onAddProject, onImportProject }} />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Add project' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import project' })).toBeInTheDocument();
  });

  it('clicking a shared-only card calls onSelect(id, "shared")', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const fakeApi = configuredApi();
    renderWithApi(<ProjectsPage projects={[]} actions={{ onSelect }} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByText('demo-repo'));

    expect(onSelect).toHaveBeenCalledWith('shared-1', 'shared');
  });

  it('shows "· stale" in the toolbar sync indicator when the listing is stale (no em-dash)', async () => {
    const fakeApi = configuredApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [{ id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z' }],
        lastSynced: '2026-07-16T00:00:00Z',
        stale: true,
      })),
    });
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText(/synced .* · stale/)).toBeInTheDocument());
    const label = screen.getByText(/synced .* · stale/);
    expect(label.textContent).not.toMatch(/—/);
  });

  // relativeTime() returns 'today'/'yesterday' with no trailing "ago" for a
  // same-day/one-day-old timestamp (see components/LastFetchedLine.jsx). This
  // locks in the exact "synced today · stale" rendering in the toolbar.
  it('renders "synced today · stale" when lastSynced is same-day', async () => {
    const fakeApi = configuredApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [{ id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z' }],
        lastSynced: new Date().toISOString(),
        stale: true,
      })),
    });
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('synced today · stale')).toBeInTheDocument());
  });

  it('toolbar refresh button calls refreshShared() and re-lists', async () => {
    const user = userEvent.setup();
    const fakeApi = configuredApi();
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    // Let the mount's own background revalidate settle first, then measure
    // the manual refresh button click in isolation from it.
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(2));
    fakeApi.refreshShared.mockClear();
    fakeApi.sharedListProjects.mockClear();

    await user.click(screen.getByRole('button', { name: 'refresh' }));

    await waitFor(() => expect(fakeApi.refreshShared).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(1));
  });

  it('shared card footer offers "pull local copy"; a 409 shows an inline copy confirm', async () => {
    const user = userEvent.setup();
    const pullSharedProject = vi.fn(async (id, action) => {
      if (!action) {
        const err = new Error('Project already exists');
        err.status = 409;
        err.kind = 'same_uuid';
        throw err;
      }
      return { imported: true, projectId: id };
    });
    const fakeApi = configuredApi({ pullSharedProject });
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'pull local copy' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'copy' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'copy' }));

    await waitFor(() => expect(pullSharedProject).toHaveBeenLastCalledWith('shared-1', 'copy'));
  });

  // Important 2 (final whole-branch review): a plain (non-conflicting) pull
  // must refresh the LOCAL project list (so it shows up merged) and give the
  // user visible feedback that it landed, not silently succeed with no
  // observable change until some unrelated action reloads the list.
  it('a plain pull calls onProjectsReload and shows "pulled to local" on that card', async () => {
    const user = userEvent.setup();
    const pullSharedProject = vi.fn(async (id) => ({ imported: true, projectId: id }));
    const onProjectsReload = vi.fn(async () => {});
    const fakeApi = configuredApi({ pullSharedProject });
    renderWithApi(
      <ProjectsPage projects={[]} actions={{ onProjectsReload }} />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'pull local copy' }));

    await waitFor(() => expect(pullSharedProject).toHaveBeenCalledWith('shared-1', undefined));
    await waitFor(() => expect(onProjectsReload).toHaveBeenCalledTimes(1));
    expect(screen.getByText('pulled to local')).toBeInTheDocument();
    // The pull button for that card is replaced by the confirmation.
    expect(screen.queryByRole('button', { name: 'pull local copy' })).not.toBeInTheDocument();
  });

  it('the copy-retry path (409 then copy) also calls onProjectsReload and shows "pulled to local"', async () => {
    const user = userEvent.setup();
    const pullSharedProject = vi.fn(async (id, action) => {
      if (!action) {
        const err = new Error('Project already exists');
        err.status = 409;
        throw err;
      }
      return { imported: true, projectId: id };
    });
    const onProjectsReload = vi.fn(async () => {});
    const fakeApi = configuredApi({ pullSharedProject });
    renderWithApi(
      <ProjectsPage projects={[]} actions={{ onProjectsReload }} />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'pull local copy' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'copy' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'copy' }));

    await waitFor(() => expect(onProjectsReload).toHaveBeenCalledTimes(1));
    expect(screen.getByText('pulled to local')).toBeInTheDocument();
  });
});

// Task 20: publish action on local cards.
describe('ProjectsPage — publish action (local cards)', () => {
  const localProjects = [
    { id: 'p1', name: 'demo-one', location: 'local' },
    { id: 'p2', name: 'demo-two', location: 'local' },
  ];

  function unconfiguredApi(overrides = {}) {
    return makeFakeApi({
      getSharedStatus: vi.fn(async () => ({ configured: false, url: null, publish: { state: 'idle' } })),
      ...overrides,
    });
  }

  function configuredLocalApi(overrides = {}) {
    return makeFakeApi({
      getSharedStatus: vi.fn(async () => ({
        configured: true,
        url: 'https://github.com/team/results.git',
        publish: { state: 'idle', project: null, runs: null, error: null, finishedAt: null },
      })),
      sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
      publishProject: vi.fn(async () => ({ started: true })),
      ...overrides,
    });
  }

  it('hides the publish button entirely when no shared repo is configured', async () => {
    const fakeApi = unconfiguredApi();
    renderWithApi(<ProjectsPage projects={localProjects} actions={{}} />, fakeApi);

    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: 'publish' })).not.toBeInTheDocument();
  });

  it('shows a publish button per local card when a shared repo is configured', async () => {
    const fakeApi = configuredLocalApi();
    renderWithApi(<ProjectsPage projects={localProjects} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getAllByRole('button', { name: 'publish' })).toHaveLength(2));
  });

  it('clicking publish calls publishProject(id), then disables every publish button and labels the clicked one "publishing..."', async () => {
    const user = userEvent.setup();
    const fakeApi = configuredLocalApi();
    renderWithApi(<ProjectsPage projects={localProjects} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getAllByRole('button', { name: 'publish' })).toHaveLength(2));

    const [firstBtn] = screen.getAllByRole('button', { name: 'publish' });
    await user.click(firstBtn);

    await waitFor(() => expect(fakeApi.publishProject).toHaveBeenCalledWith('p1'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'publishing...' })).toBeInTheDocument());

    const publishingBtn = screen.getByRole('button', { name: 'publishing...' });
    expect(publishingBtn).toHaveAttribute('aria-disabled', 'true');

    // The other card's button keeps its "publish" label (it wasn't clicked)
    // but is disabled too -- the single global job blocks every button.
    const otherBtn = screen.getByRole('button', { name: 'publish' });
    expect(otherBtn).toHaveAttribute('aria-disabled', 'true');
  });

  it('shows the API error message verbatim under the footer on a failed publish', async () => {
    const user = userEvent.setup();
    const fakeApi = configuredLocalApi({
      publishProject: vi.fn(async () => { throw new Error('a publish is already running'); }),
    });
    renderWithApi(<ProjectsPage projects={localProjects} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getAllByRole('button', { name: 'publish' })).toHaveLength(2));
    await user.click(screen.getAllByRole('button', { name: 'publish' })[0]);

    await waitFor(() => expect(screen.getByText('a publish is already running')).toBeInTheDocument());
  });

  it('shows "published <relative time>" on the card once the job completes, after re-fetching the shared list', async () => {
    // Fake timers are live for the whole test (real timers never elapse
    // 2s here). userEvent internally schedules with setTimeout too, so
    // this uses fireEvent (synchronous, no internal timers) for the click,
    // and `advanceTimersByTimeAsync` (which also flushes microtasks between
    // ticks) instead of `waitFor` to progress past each async step.
    //
    // Both useSharedProjects (always mounted) and usePublish (mounted since
    // there are local projects) independently call getSharedStatus /
    // sharedListProjects now, so exact call counts are no longer a stable
    // thing to assert on -- a mutable flag drives both mocks' responses
    // instead of a fixed once/once sequence, so this holds regardless of
    // how many times either hook happens to call them before the flip.
    vi.useFakeTimers();
    try {
      let publishDone = false;
      const getSharedStatus = vi.fn(async () => ({
        configured: true,
        publish: publishDone
          ? { state: 'done', project: 'p1', runs: 2 }
          : { state: 'idle', project: null, runs: null, error: null, finishedAt: null },
      }));
      const sharedListProjects = vi.fn(async () => (publishDone
        ? {
          projects: [{ id: 'p1', name: 'demo-one', publishedAt: '2026-07-16T00:00:00Z' }],
          lastSynced: '2026-07-17T00:00:00Z',
          stale: false,
        }
        : { projects: [], lastSynced: null, stale: false }));
      const fakeApi = configuredLocalApi({ getSharedStatus, sharedListProjects });
      renderWithApi(<ProjectsPage projects={localProjects} actions={{}} />, fakeApi);

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.getAllByRole('button', { name: 'publish' })).toHaveLength(2);

      fireEvent.click(screen.getAllByRole('button', { name: 'publish' })[0]);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(fakeApi.publishProject).toHaveBeenCalledWith('p1');

      publishDone = true;
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });

      expect(screen.getByText(/published /)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  // Audit C4 regression lock (final whole-branch review + Task 6): the old
  // fix routed post-publish completion through ProjectsPage's own effect
  // calling shared.refresh() -- a full remote git fetch that can take up to
  // 30s -- so the PUBLISHED badge/no-button state lagged behind the
  // "published <relative time>" meta line (which updated off usePublish's
  // own cheap refetch) by however long that fetch took. usePublish now owns
  // completion end to end: it optimistically upserts the published id into
  // the shared list cache the instant the job reports 'done' (see
  // usePublish.js's applyOptimisticPublish), synchronously before its own
  // authoritative re-list call even starts. Since useSharedProjects reads
  // that SAME cache entry (sharedKeys.list(), unified in Task 5), the badge
  // and the button both flip in that same render -- proven here by holding
  // the authoritative re-list open and asserting the card has already
  // flipped before it resolves.
  it('post-publish: the card flips to PUBLISHED with no publish button immediately, before the authoritative refresh resolves (C4 regression lock)', async () => {
    vi.useFakeTimers();
    try {
      let publishDone = false;
      const getSharedStatus = vi.fn(async () => ({
        configured: true,
        publish: publishDone
          ? { state: 'done', project: 'p1', runs: 2 }
          : { state: 'idle', project: null, runs: null, error: null, finishedAt: null },
      }));
      let resolveList;
      const sharedListProjects = vi.fn(() => {
        if (!publishDone) return Promise.resolve({ projects: [], lastSynced: null, stale: false });
        // Held pending once the job is done -- the card must already show
        // PUBLISHED/no-button from the optimistic patch alone, before this
        // authoritative call ever resolves.
        return new Promise((resolve) => { resolveList = resolve; });
      });
      const fakeApi = configuredLocalApi({ getSharedStatus, sharedListProjects });
      renderWithApi(<ProjectsPage projects={localProjects} actions={{}} />, fakeApi);

      // Drain the mount-time cascade (status -> list -> background
      // revalidate) before touching the publish flow -- see the sibling
      // test above for why runOnlyPendingTimersAsync is needed here instead
      // of a fixed number of advanceTimersByTimeAsync(0) calls.
      await act(async () => { await vi.runOnlyPendingTimersAsync(); });
      expect(screen.getAllByRole('button', { name: 'publish' })).toHaveLength(2);

      fireEvent.click(screen.getAllByRole('button', { name: 'publish' })[0]);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(fakeApi.publishProject).toHaveBeenCalledWith('p1');

      publishDone = true;
      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });

      // The authoritative refresh is still pending (captured but not yet
      // resolved) -- the card must already reflect completion regardless.
      expect(resolveList).toBeDefined();
      expect(screen.getByText('PUBLISHED')).toBeInTheDocument();
      // p1's own publish button is gone; p2 (never published) still has one.
      expect(screen.getAllByRole('button', { name: 'publish' })).toHaveLength(1);

      // Resolving the refresh with authoritative data must not regress the
      // card -- it only overwrites the optimistic entry.
      await act(async () => {
        resolveList({
          projects: [{ id: 'p1', name: 'demo-one', publishedAt: '2026-07-19T00:00:00Z' }],
          lastSynced: '2026-07-19T00:00:00Z',
          stale: false,
        });
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText('PUBLISHED')).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: 'publish' })).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });
});

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
