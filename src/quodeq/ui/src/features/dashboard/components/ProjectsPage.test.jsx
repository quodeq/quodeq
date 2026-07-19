import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import ProjectsPage from './ProjectsPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

// Task 18: local/online sub-tabs + shared-repo browse states.
// Task 20: publish action -- the local tab now fetches shared status/list
// on mount too (see usePublish.js), so every render with a non-empty local
// project list needs an ApiProvider from here on (previously the local tab
// never touched the API at all).
function makeFakeApi(overrides = {}) {
  return {
    getSharedStatus: vi.fn(async () => ({ configured: false, url: null, publish: { state: 'idle' } })),
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

describe('ProjectsPage — local/online tab row', () => {
  it('renders both tabs, with local active by default', () => {
    render(<ProjectsPage projects={[]} actions={{}} />);
    const local = screen.getByRole('tab', { name: 'local' });
    const online = screen.getByRole('tab', { name: 'online' });
    expect(local).toHaveAttribute('aria-selected', 'true');
    expect(online).toHaveAttribute('aria-selected', 'false');
  });

  it('marks the online tab active when sourceTab="online"', () => {
    const fakeApi = makeFakeApi();
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{}} />, fakeApi);
    expect(screen.getByRole('tab', { name: 'online' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'local' })).toHaveAttribute('aria-selected', 'false');
  });

  it('clicking the online tab calls actions.onTabChange("online") — nav-param driven, not local state', async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    render(<ProjectsPage projects={[]} actions={{ onTabChange }} />);
    await user.click(screen.getByRole('tab', { name: 'online' }));
    expect(onTabChange).toHaveBeenCalledWith('online');
  });

  it('clicking the local tab calls actions.onTabChange("local")', async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    const fakeApi = makeFakeApi();
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{ onTabChange }} />, fakeApi);
    await user.click(screen.getByRole('tab', { name: 'local' }));
    expect(onTabChange).toHaveBeenCalledWith('local');
  });

  it('re-clicking the already-active tab is a no-op -- does not call onTabChange (nav-stack dedup guard)', async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    render(<ProjectsPage projects={[]} actions={{ onTabChange }} />);

    const local = screen.getByRole('tab', { name: 'local' });
    await user.click(local);
    await user.click(local);
    expect(onTabChange).not.toHaveBeenCalled();

    const online = screen.getByRole('tab', { name: 'online' });
    await user.click(online);
    expect(onTabChange).toHaveBeenCalledTimes(1);
    expect(onTabChange).toHaveBeenCalledWith('online');
  });

  it('local tab body (cards/empty-state) is unaffected by the new tab row', async () => {
    const projects = [{ id: 'a', name: 'one', location: 'local' }];
    const fakeApi = makeFakeApi();
    renderWithApi(<ProjectsPage projects={projects} actions={{}} />, fakeApi);
    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(screen.getByText('one')).toBeInTheDocument();
  });
});

describe('ProjectsPage — online tab, unconfigured', () => {
  it('shows the connect empty state and calls connectShared(url) on submit', async () => {
    const user = userEvent.setup();
    const fakeApi = makeFakeApi();
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{}} />, fakeApi);

    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());
    expect(screen.getByText('Connect a shared results repository')).toBeInTheDocument();

    const input = screen.getByRole('textbox');
    await user.type(input, 'https://github.com/team/results.git');
    await user.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => expect(fakeApi.connectShared).toHaveBeenCalledWith('https://github.com/team/results.git'));
  });

  it('shows an inline error from the API on a failed connect', async () => {
    const user = userEvent.setup();
    const fakeApi = makeFakeApi({
      connectShared: vi.fn(async () => { throw new Error('not a valid git repository'); }),
    });
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{}} />, fakeApi);
    await waitFor(() => expect(fakeApi.getSharedStatus).toHaveBeenCalled());

    const input = screen.getByRole('textbox');
    await user.type(input, 'not-a-url');
    await user.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => expect(screen.getByText('not a valid git repository')).toBeInTheDocument());
  });
});

describe('ProjectsPage — online tab, configured', () => {
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

  it('renders the repo shorthand + project count and cards with "published by"', async () => {
    const fakeApi = configuredApi();
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    expect(screen.getByText(/github\.com\/team\/results/)).toBeInTheDocument();
    expect(screen.getByText(/1 shared project/)).toBeInTheDocument();
    expect(screen.getByText(/published by ana/)).toBeInTheDocument();
  });

  it('clicking an online card calls onSelect(id, "shared")', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const fakeApi = configuredApi();
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{ onSelect }} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByText('demo-repo'));

    expect(onSelect).toHaveBeenCalledWith('shared-1', 'shared');
  });

  it('shows the stale banner (no em-dash) when the listing is stale', async () => {
    const fakeApi = configuredApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [{ id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z' }],
        lastSynced: '2026-07-16T00:00:00Z',
        stale: true,
      })),
    });
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText(/refresh failed, showing results synced/)).toBeInTheDocument());
    const banner = screen.getByText(/refresh failed, showing results synced/);
    expect(banner.textContent).not.toMatch(/—/);
  });

  // relativeTime() returns 'today'/'yesterday' with no trailing "ago" for a
  // same-day/one-day-old timestamp (see components/LastFetchedLine.jsx).
  // Per the controller ruling, that copy is acceptable as-is -- the banner
  // just has to reuse the identical label the sync line shows. This locks
  // in the exact "synced today" rendering alongside the existing
  // day(s)-old "ago" case above.
  it('renders "refresh failed, showing results synced today" when lastSynced is same-day, using the same label as the sync line', async () => {
    const fakeApi = configuredApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [{ id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z' }],
        lastSynced: new Date().toISOString(),
        stale: true,
      })),
    });
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('refresh failed, showing results synced today')).toBeInTheDocument());
    expect(screen.getByText('synced today')).toBeInTheDocument();
  });

  it('refresh button calls refreshShared() and re-lists', async () => {
    const user = userEvent.setup();
    const fakeApi = configuredApi();
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(1);

    // Two "refresh" buttons exist (the sync-status line and each card's
    // footer) -- the sync line's is the first in document order.
    await user.click(screen.getAllByRole('button', { name: 'refresh' })[0]);

    await waitFor(() => expect(fakeApi.refreshShared).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(2));
  });

  it('online card footer offers "pull local copy"; a 409 shows an inline copy confirm', async () => {
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
    renderWithApi(<ProjectsPage projects={[]} sourceTab="online" actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'pull local copy' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'copy' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'copy' }));

    await waitFor(() => expect(pullSharedProject).toHaveBeenLastCalledWith('shared-1', 'copy'));
  });

  // Important 2 (final whole-branch review): a plain (non-conflicting) pull
  // must refresh the LOCAL project list (so the local tab is current) and
  // give the user visible feedback that it landed, not silently succeed with
  // no observable change until some unrelated action reloads the list.
  it('a plain pull calls onProjectsReload and shows "pulled to local" on that card', async () => {
    const user = userEvent.setup();
    const pullSharedProject = vi.fn(async (id) => ({ imported: true, projectId: id }));
    const onProjectsReload = vi.fn(async () => {});
    const fakeApi = configuredApi({ pullSharedProject });
    renderWithApi(
      <ProjectsPage projects={[]} sourceTab="online" actions={{ onProjectsReload }} />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'pull local copy' }));

    await waitFor(() => expect(pullSharedProject).toHaveBeenCalledWith('shared-1', undefined));
    await waitFor(() => expect(onProjectsReload).toHaveBeenCalledTimes(1));
    expect(screen.getByText('pulled to local')).toBeInTheDocument();
    // The pull/refresh buttons for that card are replaced by the confirmation.
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
      <ProjectsPage projects={[]} sourceTab="online" actions={{ onProjectsReload }} />,
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

// Task 20: publish action on LOCAL cards.
describe('ProjectsPage — local tab, publish action', () => {
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
        publish: { state: 'idle', project: null, runs: null, error: null, finished_at: null },
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
    vi.useFakeTimers();
    try {
      const getSharedStatus = vi.fn()
        .mockResolvedValueOnce({
          configured: true, publish: { state: 'idle', project: null, runs: null, error: null, finished_at: null },
        })
        .mockResolvedValueOnce({ configured: true, publish: { state: 'done', project: 'p1', runs: 2 } });
      const sharedListProjects = vi.fn()
        .mockResolvedValueOnce({ projects: [], lastSynced: null, stale: false })
        .mockResolvedValueOnce({
          projects: [{ id: 'p1', name: 'demo-one', publishedAt: '2026-07-16T00:00:00Z' }],
          lastSynced: '2026-07-17T00:00:00Z',
          stale: false,
        });
      const fakeApi = configuredLocalApi({ getSharedStatus, sharedListProjects });
      renderWithApi(<ProjectsPage projects={localProjects} actions={{}} />, fakeApi);

      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.getAllByRole('button', { name: 'publish' })).toHaveLength(2);

      fireEvent.click(screen.getAllByRole('button', { name: 'publish' })[0]);
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(fakeApi.publishProject).toHaveBeenCalledWith('p1');

      await act(async () => { await vi.advanceTimersByTimeAsync(2000); });

      expect(screen.getByText(/published /)).toBeInTheDocument();
      expect(sharedListProjects).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });
});
