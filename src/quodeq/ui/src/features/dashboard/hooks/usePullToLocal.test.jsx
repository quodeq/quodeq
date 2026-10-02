import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { usePullToLocal } from './usePullToLocal.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import catalog from '../../../strings/en.json' with { type: 'json' };

const showToast = vi.fn();
vi.mock('../../side-pane/SidePaneContext.jsx', () => ({
  useSidePane: () => ({ showToast }),
}));

const idle = { state: 'idle', phase: null };
const running = { state: 'running', phase: 'downloading', project: 'proj-1' };
const done = { state: 'done', phase: 'done', project: 'proj-1', projectId: 'local-1', finishedAt: 5 };
const collision = {
  state: 'error', phase: 'error', project: 'proj-1', code: 'PROJECT_EXISTS',
  conflictKind: 'same_uuid', sourceProjectId: 'local-1', finishedAt: 6,
};

// The pull slot is part of useSharedProjects' result; rerender plays the poll.
function setup(initialSlot, pull = vi.fn().mockResolvedValue({ started: true })) {
  const hook = renderHook(
    ({ slot }) => usePullToLocal({ shared: { pull, pullSlot: slot } }),
    { wrapper: withQueryClient(), initialProps: { slot: initialSlot } },
  );
  return { ...hook, pull };
}

describe('usePullToLocal', () => {
  beforeEach(() => {
    showToast.mockClear();
  });

  it('handlePull starts the job through shared.pull and handleConfirmCopy asks for a copy', async () => {
    const { result, pull } = setup(idle);

    await act(async () => { await result.current.handlePull('proj-1'); });
    await act(async () => { await result.current.handleConfirmCopy('proj-1'); });

    expect(pull).toHaveBeenNthCalledWith(1, 'proj-1', undefined);
    expect(pull).toHaveBeenNthCalledWith(2, 'proj-1', 'copy');
  });

  it('a pull that is running in the slot reports pulling for that project', () => {
    const { result } = setup(running);
    expect(result.current.pullingId).toBe('proj-1');
    expect(result.current.pulledIds.size).toBe(0);
  });

  it('a pull that reaches DONE marks the project pulled, without refetching the projects list itself', () => {
    const invalidate = vi.spyOn(QueryClient.prototype, 'invalidateQueries');
    const { result, rerender } = setup(idle);

    rerender({ slot: running });
    rerender({ slot: done });

    expect(result.current.pulledIds.has('proj-1')).toBe(true);
    expect(result.current.pullingId).toBeNull();
    // useSyncStatus invalidates projectsKeys.list() on the DONE transition.
    expect(invalidate).not.toHaveBeenCalled();
    invalidate.mockRestore();
  });

  it('a finished pull already in the slot when the hook mounts is not shown as pulled', () => {
    const { result } = setup(done);
    expect(result.current.pulledIds.size).toBe(0);
  });

  it('a PROJECT_EXISTS error opens the conflict, carrying the collision kind, and cancel closes it', () => {
    const { result, rerender } = setup(idle);

    rerender({ slot: collision });
    expect(result.current.pullConflictId).toBe('proj-1');
    expect(result.current.pullConflict).toEqual({ kind: 'same_uuid', projectId: 'local-1' });
    expect(showToast).not.toHaveBeenCalled();

    act(() => result.current.cancelConflict());
    expect(result.current.pullConflictId).toBeNull();
  });

  it('starting the copy closes the conflict at once, before the next poll lands', async () => {
    const { result, rerender } = setup(idle);
    rerender({ slot: collision });

    await act(async () => { await result.current.handleConfirmCopy('proj-1'); });

    expect(result.current.pullConflictId).toBeNull();
  });

  it('another pull error shows the mapped translation once, not the raw backend message', () => {
    const { result, rerender } = setup(idle);
    const failed = { state: 'error', phase: 'error', project: 'proj-1', code: 'CONNECT_FAILED', error: 'raw backend sentence', finishedAt: 7 };

    rerender({ slot: failed });
    rerender({ slot: { ...failed } });

    expect(showToast).toHaveBeenCalledTimes(1);
    expect(showToast).toHaveBeenCalledWith(catalog['apiError.connectFailed']);
    expect(result.current.pullConflictId).toBeNull();
  });

  it('handlePull surfaces a failure to start via showToast, not window.alert', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const { result } = setup(idle, vi.fn().mockRejectedValue({ status: 500, message: 'boom' }));

    await act(async () => { await result.current.handlePull('proj-1'); });

    expect(alertSpy).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledTimes(1);
    alertSpy.mockRestore();
  });

  it('handleConfirmCopy surfaces a failure to start via showToast', async () => {
    const { result } = setup(idle, vi.fn().mockRejectedValue({ status: 500, message: 'boom' }));

    await act(async () => { await result.current.handleConfirmCopy('proj-1'); });

    expect(showToast).toHaveBeenCalledTimes(1);
  });

  it('a failure to start with a mapped code shows the translation, not the raw message', async () => {
    const { result } = setup(idle, vi.fn().mockRejectedValue({ status: 409, code: 'PROJECT_EXISTS', message: 'raw backend sentence' }));

    await act(async () => { await result.current.handlePull('proj-1'); });

    expect(showToast).toHaveBeenCalledWith(catalog['apiError.projectExists']);
  });

  it('a failure to start with no message falls back to the bare pullFailed string', async () => {
    const { result } = setup(idle, vi.fn().mockRejectedValue({ status: 500 }));

    await act(async () => { await result.current.handlePull('proj-1'); });

    expect(showToast).toHaveBeenCalledWith(catalog['projects.pullFailed']);
    expect(showToast.mock.calls[0][0]).not.toMatch(/\{message\}/);
  });
});
