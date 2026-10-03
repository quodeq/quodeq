import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { QueryClient } from '@tanstack/react-query';
import { projectsKeys } from '../api/queryKeys.js';
import { useJobCompletionEffect } from './useJobCompletionEffect.js';
import { JOB_STATUS } from '../vocab/jobStatus.js';

const PROJECTS_LIST = { queryKey: projectsKeys.list() };

function renderEffect(job) {
  const queryClient = new QueryClient();
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const props = { job, navTab: vi.fn(), queryClient, selectedProject: null, selectProjectAndRun: vi.fn() };
  const utils = renderHook((p) => useJobCompletionEffect(p), { initialProps: props });
  return { ...utils, invalidate, props };
}

describe('useJobCompletionEffect project-list refresh', () => {
  it('invalidates the project list when a job finishes with a run', () => {
    const { invalidate } = renderEffect({ status: JOB_STATUS.DONE, outputProject: 'p1', outputRunId: 'r1' });
    expect(invalidate).toHaveBeenCalledWith(PROJECTS_LIST);
  });

  it('does not invalidate the project list while the job is still running', () => {
    const { invalidate } = renderEffect({ status: JOB_STATUS.RUNNING, outputProject: 'p1', outputRunId: 'r1' });
    expect(invalidate).not.toHaveBeenCalledWith(PROJECTS_LIST);
  });

  it('invalidates once per finished run, not on every re-render', () => {
    const job = { status: JOB_STATUS.DONE, outputProject: 'p1', outputRunId: 'r1' };
    const { invalidate, rerender, props } = renderEffect(job);
    rerender({ ...props, job: { ...job } });
    const listCalls = invalidate.mock.calls.filter(([arg]) => JSON.stringify(arg) === JSON.stringify(PROJECTS_LIST));
    expect(listCalls).toHaveLength(1);
  });
});
