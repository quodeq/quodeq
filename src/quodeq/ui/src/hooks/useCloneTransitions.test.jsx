import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectsKeys } from '../api/queryKeys.js';
import { SYNC_PHASE } from '../vocab/syncPhase.js';
import { CLONE_CODE_PROJECT_EXISTS } from '../api/projectClone.js';
import { useCloneTransitions, landedProjectId } from './useCloneTransitions.js';

const REPO = 'https://github.com/acme/billing.git';
const idle = { state: 'idle', kind: 'clone', phase: null, repo: '', finishedAt: null };
const running = { state: 'running', kind: 'clone', phase: SYNC_PHASE.DOWNLOADING, percent: 10, repo: REPO, finishedAt: null };
const done = { ...running, state: 'done', phase: SYNC_PHASE.DONE, percent: 100, projectId: 'p-new', finishedAt: 7 };
const exists = { ...running, state: 'error', phase: SYNC_PHASE.ERROR, code: CLONE_CODE_PROJECT_EXISTS, error: 'already there', detail: 'p-old', finishedAt: 9 };
const failed = { ...running, state: 'error', phase: SYNC_PHASE.ERROR, code: 'REPO_NOT_FOUND', error: 'nope', detail: '', finishedAt: 11 };

function setup(first = idle) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const current = { slot: first };
  const api = { getCloneStatus: vi.fn(async () => current.slot) };
  const onLanded = vi.fn();
  const invalidate = vi.spyOn(qc, 'invalidateQueries');
  renderHook(() => useCloneTransitions({ onLanded, activeMs: 100000, idleMs: 100000 }), {
    wrapper: ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>,
  });
  // Plays the next poll landing.
  const poll = (slot) => act(() => { current.slot = slot; qc.setQueryData(projectsKeys.clone(), slot); });
  return { api, onLanded, invalidate, poll, qc };
}

describe('landedProjectId', () => {
  it('is the new project on DONE, the existing one on PROJECT_EXISTS, nothing otherwise', () => {
    expect(landedProjectId(done)).toBe('p-new');
    expect(landedProjectId(exists)).toBe('p-old');
    expect(landedProjectId(failed)).toBeNull();
    expect(landedProjectId(running)).toBeNull();
    expect(landedProjectId(undefined)).toBeNull();
  });
});

describe('useCloneTransitions', () => {
  it('a clone that lands re-lists the projects and hands the new project over once', async () => {
    const { api, onLanded, invalidate, poll } = setup();
    await waitFor(() => expect(api.getCloneStatus).toHaveBeenCalled());
    await poll(running);
    await poll(done);
    await waitFor(() => expect(onLanded).toHaveBeenCalledTimes(1));
    expect(onLanded.mock.calls[0][0].projectId).toBe('p-new');
    expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({ queryKey: projectsKeys.list() }));
    await poll({ ...done });
    expect(onLanded).toHaveBeenCalledTimes(1);
  });

  it('a url that is already a project lands on the existing project', async () => {
    const { api, onLanded, poll } = setup();
    await waitFor(() => expect(api.getCloneStatus).toHaveBeenCalled());
    await poll(running);
    await poll(exists);
    await waitFor(() => expect(onLanded).toHaveBeenCalledTimes(1));
    expect(onLanded.mock.calls[0][0].projectId).toBe('p-old');
  });

  it('a failed clone lands nothing', async () => {
    const { api, onLanded, poll } = setup();
    await waitFor(() => expect(api.getCloneStatus).toHaveBeenCalled());
    await poll(running);
    await poll(failed);
    await act(async () => {});
    expect(onLanded).not.toHaveBeenCalled();
  });

  it('a finished slot already in the cache at mount is no landing', async () => {
    const { api, onLanded } = setup(done);
    await waitFor(() => expect(api.getCloneStatus).toHaveBeenCalled());
    await act(async () => {});
    expect(onLanded).not.toHaveBeenCalled();
  });
});
