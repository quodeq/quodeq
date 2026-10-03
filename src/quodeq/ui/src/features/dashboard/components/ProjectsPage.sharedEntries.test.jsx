import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ProjectsPage from './ProjectsPage.jsx';
import { QueryClient } from '@tanstack/react-query';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { projectsKeys } from '../../../api/queryKeys.js';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

// The invalidateQueries spy patches QueryClient.prototype, so it is restored
// even when an assertion fails, or it would leak into later tests.
let invalidateSpy = null;
function spyOnInvalidate() {
  invalidateSpy = vi.spyOn(QueryClient.prototype, 'invalidateQueries');
  return invalidateSpy;
}
afterEach(() => {
  invalidateSpy?.mockRestore();
  invalidateSpy = null;
});

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


// Split from ProjectsPage.test.jsx: shared-only cards (configured
// shared repo) — rendering, the strip's stale state, and the pull flow.

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
  // empty page's two paths don't render either). Gate on `isEmpty` instead.
  it('shows the add project header button with zero local projects but a shared project present', async () => {
    const onAddProject = vi.fn();
    const onImportProject = vi.fn();
    const fakeApi = configuredApi();
    renderWithApi(
      <ProjectsPage projects={[]} actions={{ onAddProject, onImportProject }} />,
      fakeApi,
    );

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Add project' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Import evaluations' })).not.toBeInTheDocument();
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

  it('a stale listing shows "update failed · showing results from <when>" in the strip (no em-dash)', async () => {
    const fakeApi = configuredApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [{ id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z' }],
        lastSynced: '2026-07-16T00:00:00Z',
        stale: true,
      })),
    });
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText(/update failed · showing results from .* ago/)).toBeInTheDocument());
    const label = screen.getByText(/update failed · showing results from/);
    expect(label.textContent).not.toMatch(/—/);
    expect(screen.getByRole('button', { name: 'retry' })).toBeInTheDocument();
  });

  // relativeTimeFine() reads "just now" for a timestamp under a minute old.
  it('renders "showing results from just now" when lastSynced is this minute', async () => {
    const fakeApi = configuredApi({
      sharedListProjects: vi.fn(async () => ({
        projects: [{ id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z' }],
        lastSynced: new Date().toISOString(),
        stale: true,
      })),
    });
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText(/update failed · showing results from just now/)).toBeInTheDocument());
  });

  it('the strip\'s update button starts a refresh job and the list refetches when it finishes', async () => {
    const user = userEvent.setup();
    const slots = { refresh: { state: 'idle', phase: null } };
    const fakeApi = configuredApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git', ...slots })),
      startRefresh: vi.fn(async () => { slots.refresh = { state: 'done', phase: 'done' }; return { started: true }; }),
    });
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    // Mounting never starts a refresh on its own.
    expect(fakeApi.startRefresh).not.toHaveBeenCalled();
    fakeApi.sharedListProjects.mockClear();

    await user.click(screen.getByRole('button', { name: 'update evaluations repository' }));

    await waitFor(() => expect(fakeApi.startRefresh).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(fakeApi.sharedListProjects).toHaveBeenCalledTimes(1));
    expect(fakeApi.sharedListProjects).toHaveBeenLastCalledWith({ refresh: false });
  });

  // The pull is a background job: startPull answers 202 and the outcome is
  // read from the pull slot of the status. This fake plays the server: the
  // first pull of a project that "exists" lands in ERROR/PROJECT_EXISTS, the
  // copy (or any other) pull lands in DONE.
  function pullApi({ collide }) {
    const slots = { pull: { state: 'idle', phase: null } };
    return configuredApi({
      getSharedStatus: vi.fn(async () => ({ configured: true, url: 'https://github.com/team/results.git', ...slots })),
      startPull: vi.fn(async (project, action) => {
        slots.pull = collide && !action
          ? { state: 'error', phase: 'error', project, code: 'PROJECT_EXISTS', conflictKind: 'same_uuid', sourceProjectId: 'local-1', finishedAt: 1 }
          : { state: 'done', phase: 'done', project, projectId: 'local-1', finishedAt: 2 };
        return { started: true, project };
      }),
    });
  }

  it('shared card footer offers "pull local copy"; a collision shows an inline copy confirm', async () => {
    const user = userEvent.setup();
    const fakeApi = pullApi({ collide: true });
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'pull local copy' }));

    await waitFor(() => expect(screen.getByRole('button', { name: 'copy' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'copy' }));

    await waitFor(() => expect(fakeApi.startPull).toHaveBeenLastCalledWith('shared-1', 'copy'));
  });

  // A plain (non-conflicting) pull must refresh the LOCAL project list (so it
  // shows up merged) and give the user visible feedback that it landed.
  it('a plain pull refetches the project list and shows "pulled to local" on that card', async () => {
    const user = userEvent.setup();
    const invalidate = spyOnInvalidate();
    const projectListRefetches = () => invalidate.mock.calls.filter(([arg]) => (
      JSON.stringify(arg?.queryKey) === JSON.stringify(projectsKeys.list())
    )).length;
    const fakeApi = pullApi({ collide: false });
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'pull local copy' }));

    await waitFor(() => expect(fakeApi.startPull).toHaveBeenCalledWith('shared-1', undefined));
    await waitFor(() => expect(screen.getByText('pulled to local')).toBeInTheDocument());
    expect(projectListRefetches()).toBe(1);
    // The pull button for that card is replaced by the confirmation.
    expect(screen.queryByRole('button', { name: 'pull local copy' })).not.toBeInTheDocument();
  });

  it('the copy-retry path (collision then copy) also refetches the project list and shows "pulled to local"', async () => {
    const user = userEvent.setup();
    const invalidate = spyOnInvalidate();
    const projectListRefetches = () => invalidate.mock.calls.filter(([arg]) => (
      JSON.stringify(arg?.queryKey) === JSON.stringify(projectsKeys.list())
    )).length;
    const fakeApi = pullApi({ collide: true });
    renderWithApi(<ProjectsPage projects={[]} actions={{}} />, fakeApi);

    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'pull local copy' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'copy' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'copy' }));

    await waitFor(() => expect(screen.getByText('pulled to local')).toBeInTheDocument());
    expect(projectListRefetches()).toBe(1);
  });
});
