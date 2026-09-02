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


// Split from ProjectsPage.test.jsx: the publish action on local cards
// (button gating, in-flight state, error surfacing, and completion).

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
