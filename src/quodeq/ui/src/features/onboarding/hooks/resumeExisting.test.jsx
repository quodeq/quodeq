import { describe, it, expect, vi } from 'vitest';
import { makeTryResumeExisting, resumedExisting } from './resumeExisting.js';

describe('makeTryResumeExisting', () => {
  it('resumes a registered project with no evaluations into its scan', async () => {
    const actions = { succeedScan: vi.fn() };
    const getProjectScan = vi.fn(async () => ({ total_files: 3 }));
    const tryResume = makeTryResumeExisting({ getProjectInfo: async () => ({ runsCount: 0 }), getProjectScan, actions });
    expect(await tryResume('p1')).toBe(true);
    expect(actions.succeedScan).toHaveBeenCalledWith('p1', { total_files: 3 });
  });

  it('leaves a project that already has evaluations alone', async () => {
    const actions = { succeedScan: vi.fn() };
    const getProjectScan = vi.fn();
    const tryResume = makeTryResumeExisting({ getProjectInfo: async () => ({ runsCount: 2 }), getProjectScan, actions });
    expect(await tryResume('p1')).toBe(false);
    expect(getProjectScan).not.toHaveBeenCalled();
  });

  it('a failing read falls back to the error path', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const tryResume = makeTryResumeExisting({
      getProjectInfo: async () => { throw new Error('boom'); }, getProjectScan: vi.fn(), actions: { succeedScan: vi.fn() },
    });
    expect(await tryResume('p1')).toBe(false);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe('resumedExisting', () => {
  it('only a 409 carrying the existing project id resumes', async () => {
    const tryResume = vi.fn(async () => true);
    expect(await resumedExisting({ status: 500, existingProjectId: 'p1' }, tryResume)).toBe(false);
    expect(await resumedExisting({ status: 409 }, tryResume)).toBe(false);
    expect(tryResume).not.toHaveBeenCalled();
    expect(await resumedExisting({ status: 409, existingProjectId: 'p1' }, tryResume)).toBe(true);
    expect(tryResume).toHaveBeenCalledWith('p1');
  });
});
