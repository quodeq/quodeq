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


// Split from ProjectsPage.test.jsx: shared-only cards (configured
// shared repo) — rendering, sync indicator states, and the pull flow.

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
