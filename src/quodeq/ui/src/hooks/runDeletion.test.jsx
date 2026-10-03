import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { nextSelectedRunAfterDelete, useHandleRunDeleted } from './runDeletion.js';
import { LATEST_RUN_ID } from '../constants.js';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { projectsKeys } from '../api/queryKeys.js';

function withSpiedClient() {
  const queryClient = new QueryClient();
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const wrapper = ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  return { wrapper, invalidate };
}

describe('nextSelectedRunAfterDelete', () => {
  it('resets to latest when the deleted run was selected', () => {
    expect(nextSelectedRunAfterDelete('run-B', 'run-B')).toBe(LATEST_RUN_ID);
  });
  it('keeps the selection otherwise', () => {
    expect(nextSelectedRunAfterDelete('run-A', 'run-B')).toBe('run-A');
    expect(nextSelectedRunAfterDelete(LATEST_RUN_ID, 'run-B')).toBe(LATEST_RUN_ID);
  });
});

describe('useHandleRunDeleted', () => {
  function deps(historySelectedRun) {
    return {
      dropRunFromCache: vi.fn(), setSelectedRun: vi.fn(), historySelectedRun, setHistorySelectedRun: vi.fn(),
      scheduleDashboardReconcile: vi.fn(),
    };
  }

  it('drops the run, moves an Overview selection off it, reconciles and reloads projects', () => {
    const d = deps('run-A');
    const { wrapper, invalidate } = withSpiedClient();
    const { result } = renderHook(() => useHandleRunDeleted(d), { wrapper });
    act(() => result.current('run-B'));
    expect(d.dropRunFromCache).toHaveBeenCalledWith('run-B');
    expect(d.setSelectedRun).toHaveBeenCalledTimes(1);
    expect(d.setSelectedRun.mock.calls[0][0]('run-B')).toBe(LATEST_RUN_ID);
    expect(d.setSelectedRun.mock.calls[0][0]('run-A')).toBe('run-A');
    expect(d.setHistorySelectedRun).not.toHaveBeenCalled();
    expect(d.scheduleDashboardReconcile).toHaveBeenCalledTimes(1);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: projectsKeys.list() });
  });

  it('resets the History selection when it pointed at the deleted run', () => {
    const d = deps('run-B');
    const { result } = renderHook(() => useHandleRunDeleted(d), { wrapper: withSpiedClient().wrapper });
    act(() => result.current('run-B'));
    expect(d.setHistorySelectedRun).toHaveBeenCalledWith(LATEST_RUN_ID);
  });
});
