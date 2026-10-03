import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { projectsKeys } from '../../../api/queryKeys.js';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { useCompleteSetup } from './useCompleteSetup.js';

/**
 * useCompleteSetup backs IncompleteSetupCard's re-registration flow: it
 * must call registerProject through the injected ApiContext (never a direct
 * api/index.js import) so the card can be tested without hitting fetch.
 */
function wrapper(api, qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  const full = { getCloneStatus: vi.fn(async () => qc.getQueryData(projectsKeys.clone()) ?? null), ...api };
  return function Wrapper({ children }) {
    return <QueryClientProvider client={qc}><ApiProvider value={full}>{children}</ApiProvider></QueryClientProvider>;
  };
}

const REPO = 'https://x/y.git';
const running = { state: 'running', kind: 'clone', phase: SYNC_PHASE.DOWNLOADING, percent: 40, repo: REPO, finishedAt: null };
const done = { ...running, state: 'done', phase: SYNC_PHASE.DONE, percent: 100, projectId: 'p1', finishedAt: 2000 };
const failed = { ...running, state: 'error', phase: SYNC_PHASE.ERROR, code: 'REPO_NOT_FOUND', error: 'Repository not found', finishedAt: 3000 };

// A url answers 202 and clones as a job: the hook follows the shared clone slot.
function setupCloneJob(initial = { ...done, finishedAt: 1000 }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(projectsKeys.clone(), initial);
  const registerProject = vi.fn(async () => ({ started: true, repo: REPO, dest: '/tmp/x/y' }));
  const onComplete = vi.fn();
  const hook = renderHook(() => useCompleteSetup({ repoUrl: REPO, onComplete }), { wrapper: wrapper({ registerProject }, qc) });
  const poll = (slot) => act(() => { qc.setQueryData(projectsKeys.clone(), slot); });
  return { ...hook, onComplete, poll };
}

describe('useCompleteSetup', () => {
  it('calls registerProject (from useApi()) with the repo url and clone target', async () => {
    const registerProject = vi.fn().mockResolvedValue({ projectId: 'p1', scanData: {} });
    const onComplete = vi.fn();
    const { result } = renderHook(
      () => useCompleteSetup({ repoUrl: 'https://x/y.git', onComplete }),
      { wrapper: wrapper({ registerProject }) },
    );

    await act(async () => {
      await result.current.handleSubmit({ cloneDest: '/tmp/x', ephemeral: false });
    });

    expect(registerProject).toHaveBeenCalledWith({ repo: 'https://x/y.git', cloneDest: '/tmp/x', ephemeral: false });
    expect(onComplete).toHaveBeenCalledWith({ projectId: 'p1', scanData: {} });
    expect(result.current.submitting).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('sets a friendly error and does not call onComplete on failure', async () => {
    const registerProject = vi.fn().mockRejectedValue(Object.assign(new Error('boom'), { code: 'REGISTRATION_FAILED' }));
    const onComplete = vi.fn();
    const { result } = renderHook(
      () => useCompleteSetup({ repoUrl: 'https://x/y.git', onComplete }),
      { wrapper: wrapper({ registerProject }) },
    );

    await act(async () => {
      await result.current.handleSubmit({ cloneDest: '/tmp/x' });
    });

    expect(onComplete).not.toHaveBeenCalled();
    expect(result.current.error).toBeTruthy();
    expect(result.current.submitting).toBe(false);
  });

  it('open toggles independently, starting closed', () => {
    const registerProject = vi.fn();
    const { result } = renderHook(
      () => useCompleteSetup({ repoUrl: 'x', onComplete: vi.fn() }),
      { wrapper: wrapper({ registerProject }) },
    );
    expect(result.current.open).toBe(false);
    act(() => result.current.setOpen(true));
    expect(result.current.open).toBe(true);
  });

  it('a 202 clone job keeps submitting until its slot reaches done, then completes once', async () => {
    const { result, onComplete, poll } = setupCloneJob();
    await act(async () => { await result.current.handleSubmit({ cloneDest: '/tmp/x', ephemeral: false }); });
    expect(result.current.submitting).toBe(true);
    expect(onComplete).not.toHaveBeenCalled();
    await poll(running);
    expect(result.current.submitting).toBe(true);
    await poll(done);
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
    expect(result.current.submitting).toBe(false);
    expect(result.current.error).toBeNull();
    await poll({ ...done });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('a 202 clone job whose slot fails shows the mapped message', async () => {
    const { result, onComplete, poll } = setupCloneJob();
    await act(async () => { await result.current.handleSubmit({ cloneDest: '/tmp/x' }); });
    await poll(running);
    await poll(failed);
    await waitFor(() => expect(result.current.error).toBe(apiErrorMessage({ code: failed.code, message: failed.error }, 'overview.cloneFailed')));
    expect(result.current.submitting).toBe(false);
    expect(onComplete).not.toHaveBeenCalled();
  });
});
