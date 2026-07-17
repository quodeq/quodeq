import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import React from 'react';
import ProjectsPage from './ProjectsPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';

describe('ProjectsPage', () => {
  it('renders a "setup incomplete" badge on online-location projects', () => {
    const projects = [
      { id: 'a', name: 'local-one', location: 'local' },
      { id: 'b', name: 'online-legacy', location: 'online' },
    ];
    render(<ProjectsPage projects={projects} actions={{}} />);
    const badges = screen.queryAllByText(/setup incomplete/i);
    expect(badges).toHaveLength(1);
  });

  it('renders no badge when all projects are local', () => {
    const projects = [
      { id: 'a', name: 'one', location: 'local' },
      { id: 'b', name: 'two', location: 'local' },
    ];
    render(<ProjectsPage projects={projects} actions={{}} />);
    expect(screen.queryByText(/setup incomplete/i)).not.toBeInTheDocument();
  });
});

// Task 18: local/online sub-tabs + shared-repo browse states.
function makeFakeApi(overrides = {}) {
  return {
    getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
    connectShared: vi.fn(async (url) => ({ configured: true, url })),
    refreshShared: vi.fn(async () => ({ stale: false, lastSynced: '2026-07-17T00:00:00Z' })),
    pullSharedProject: vi.fn(async (id) => ({ imported: true, projectId: id })),
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

  it('local tab body (cards/empty-state) is unaffected by the new tab row', () => {
    const projects = [{ id: 'a', name: 'one', location: 'local' }];
    render(<ProjectsPage projects={projects} actions={{}} />);
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
});
