import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useRepoScanStep, makeHandleSubmit, makeHandleCloneTargetSubmit } from './useRepoScanStep.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';

// The direct path (a local path, or a repo already registered under a
// createProject call that isn't the clone-target sub-step) used to hand
// failScan the raw err.message instead of routing it through the same
// friendly mapper every other call site uses. `.jsx` because this hook
// pulls in the api layer, which relies on import.meta.env -- plain
// `node --test` can't load it, so this runs under vitest (`npm run test:ui`).

describe('makeHandleSubmit', () => {
  it('direct-path scan failure runs the error through apiErrorMessage', async () => {
    // AUTH_REQUIRED is a mapped code, so its friendly text diverges from the
    // raw backend message -- that divergence is what makes this test fail
    // against the old `message: err.message` code.
    const err = Object.assign(new Error('raw internal detail'), { code: 'AUTH_REQUIRED' });
    const createProject = vi.fn().mockRejectedValue(err);
    const actions = { startScan: vi.fn(), failScan: vi.fn(), succeedScan: vi.fn() };
    const handleSubmit = makeHandleSubmit({
      state: { repo: { value: 'org/repo' } },
      actions,
      createProject,
      setSubStep: vi.fn(),
      setCloneError: vi.fn(),
      tryResumeExisting: vi.fn().mockResolvedValue(false),
    });

    await handleSubmit();

    expect(actions.failScan).toHaveBeenCalledWith(
      expect.objectContaining({ message: apiErrorMessage(err, 'onboarding.scanFailed') }),
    );
    expect(actions.failScan.mock.calls[0][0].message).not.toBe(err.message);
  });

  it('git:// is no longer a remote URL: it goes to createProject as a local path', async () => {
    const createProject = vi.fn().mockResolvedValue({ projectId: 'p1', scanData: {} });
    const setSubStep = vi.fn();
    const actions = { startScan: vi.fn(), failScan: vi.fn(), succeedScan: vi.fn() };
    const handleSubmit = makeHandleSubmit({
      state: { repo: { value: 'git://x/y' } },
      actions,
      createProject,
      setSubStep,
      setCloneError: vi.fn(),
      tryResumeExisting: vi.fn().mockResolvedValue(false),
    });

    await handleSubmit();

    expect(createProject).toHaveBeenCalledWith({ repo: 'git://x/y' });
    expect(setSubStep).not.toHaveBeenCalled();
  });

  it('ssh:// enters the clone-target sub-step', async () => {
    const createProject = vi.fn();
    const setSubStep = vi.fn();
    const handleSubmit = makeHandleSubmit({
      state: { repo: { value: 'ssh://git@github.com/o/r.git' } },
      actions: { startScan: vi.fn(), failScan: vi.fn(), succeedScan: vi.fn() },
      createProject,
      setSubStep,
      setCloneError: vi.fn(),
      tryResumeExisting: vi.fn().mockResolvedValue(false),
    });

    await handleSubmit();

    expect(setSubStep).toHaveBeenCalledWith('cloneTarget');
    expect(createProject).not.toHaveBeenCalled();
  });

  it('an unmapped code keeps showing the backend message, unchanged', async () => {
    const err = Object.assign(new Error('Project not found'), { code: 'NOT_FOUND' });
    const createProject = vi.fn().mockRejectedValue(err);
    const actions = { startScan: vi.fn(), failScan: vi.fn(), succeedScan: vi.fn() };
    const handleSubmit = makeHandleSubmit({
      state: { repo: { value: 'org/repo' } },
      actions,
      createProject,
      setSubStep: vi.fn(),
      setCloneError: vi.fn(),
      tryResumeExisting: vi.fn().mockResolvedValue(false),
    });

    await handleSubmit();

    expect(actions.failScan.mock.calls[0][0].message).toBe('Project not found');
  });
});

describe('makeHandleCloneTargetSubmit', () => {
  it('clone-target scan failure runs the error through apiErrorMessage', async () => {
    // AUTH_REQUIRED is a mapped code (see apiErrors.js CODE_KEYS), so its
    // friendly text diverges from the raw backend message -- that divergence
    // is what makes this test fail against the old `message: err.message`
    // code, which forwarded err.message straight to failScan even though
    // setCloneError right above it already ran the same err through
    // apiErrorMessage.
    const err = Object.assign(new Error('raw internal detail'), { code: 'AUTH_REQUIRED' });
    const createProject = vi.fn().mockRejectedValue(err);
    const actions = { startScan: vi.fn(), failScan: vi.fn(), succeedScan: vi.fn() };
    const handleCloneTargetSubmit = makeHandleCloneTargetSubmit({
      state: { repo: { value: 'https://example.com/org/repo.git' } },
      actions,
      createProject,
      setSubStep: vi.fn(),
      setCloneError: vi.fn(),
      setCloneSubmitting: vi.fn(),
      probeGit: vi.fn().mockResolvedValue({ reachable: true, kind: 'ok' }),
      setCloneDetail: vi.fn(),
      setAccessFailure: vi.fn(),
      lastSubmitRef: { current: null },
      tryResumeExisting: vi.fn().mockResolvedValue(false),
    });

    await handleCloneTargetSubmit({ cloneDest: '/tmp/repo', ephemeral: false });

    expect(actions.failScan).toHaveBeenCalledWith(
      expect.objectContaining({ message: apiErrorMessage(err, 'onboarding.cloneFailed') }),
    );
    expect(actions.failScan.mock.calls[0][0].message).not.toBe(err.message);
    // code forwarding for downstream consumers (e.g. existingProjectId flows)
    // is unrelated to the message mapping and must survive the fix.
    expect(actions.failScan.mock.calls[0][0].code).toBe('AUTH_REQUIRED');
  });

  it('an unmapped code keeps showing the backend message, unchanged', async () => {
    const err = Object.assign(new Error('Project not found'), { code: 'NOT_FOUND' });
    const createProject = vi.fn().mockRejectedValue(err);
    const actions = { startScan: vi.fn(), failScan: vi.fn(), succeedScan: vi.fn() };
    const handleCloneTargetSubmit = makeHandleCloneTargetSubmit({
      state: { repo: { value: 'https://example.com/org/repo.git' } },
      actions,
      createProject,
      setSubStep: vi.fn(),
      setCloneError: vi.fn(),
      setCloneSubmitting: vi.fn(),
      probeGit: vi.fn().mockResolvedValue({ reachable: true, kind: 'ok' }),
      setCloneDetail: vi.fn(),
      setAccessFailure: vi.fn(),
      lastSubmitRef: { current: null },
      tryResumeExisting: vi.fn().mockResolvedValue(false),
    });

    await handleCloneTargetSubmit({ cloneDest: '/tmp/repo', ephemeral: false });

    expect(actions.failScan.mock.calls[0][0].message).toBe('Project not found');
  });
});

function renderRepoScanHook({ createProject, probeGit, repo }) {
  const actions = { startScan: vi.fn(), failScan: vi.fn(), succeedScan: vi.fn(), resetScan: vi.fn(), setRepo: vi.fn() };
  const state = { repo: { value: repo }, repoScanSubState: 'idle' };
  return renderHook(() => useRepoScanStep({ state, actions, createProject, getProjectInfo: vi.fn(), probeGit }));
}

describe('useRepoScanStep access ladder', () => {
  it('a failed probe shows the access panel and never calls createProject', async () => {
    const createProject = vi.fn();
    const probeGit = vi.fn(async () => ({ reachable: false, kind: 'not_found', detail: 'nope', host: 'github.com', isGitHub: true }));
    const { result } = renderRepoScanHook({ createProject, probeGit, repo: 'https://github.com/o/r.git' });
    await act(async () => { await result.current.handleCloneTargetSubmit({ cloneDest: '/tmp/x', ephemeral: false }); });
    expect(createProject).not.toHaveBeenCalled();
    expect(result.current.accessFailure).toEqual({ kind: 'not_found', detail: 'nope', host: 'github.com', isGitHub: true });
  });

  it('retryClone re-runs the last submit after the panel resolves', async () => {
    const createProject = vi.fn(async () => ({ projectId: 'p', scanData: {} }));
    const answers = [{ reachable: false, kind: 'auth_required', detail: '', host: 'github.com', isGitHub: true }, { reachable: true, kind: 'ok' }];
    const probeGit = vi.fn(async () => answers.shift());
    const { result } = renderRepoScanHook({ createProject, probeGit, repo: 'https://github.com/o/r.git' });
    await act(async () => { await result.current.handleCloneTargetSubmit({ cloneDest: '/tmp/x', ephemeral: false }); });
    await act(async () => { await result.current.retryClone(); });
    expect(createProject).toHaveBeenCalledWith({ repo: 'https://github.com/o/r.git', cloneDest: '/tmp/x', ephemeral: false });
    expect(result.current.accessFailure).toBeNull();
  });

  it('a retry while a clone is in flight is a no-op', async () => {
    let finish;
    const createProject = vi.fn(() => new Promise((resolve) => { finish = () => resolve({ projectId: 'p', scanData: {} }); }));
    const answers = [{ reachable: false, kind: 'auth_required', detail: '', host: 'github.com', isGitHub: true }, { reachable: true, kind: 'ok' }];
    const probeGit = vi.fn(async () => answers.shift());
    const { result } = renderRepoScanHook({ createProject, probeGit, repo: 'https://github.com/o/r.git' });
    await act(async () => { await result.current.handleCloneTargetSubmit({ cloneDest: '/tmp/x', ephemeral: false }); });
    let first;
    await act(async () => {
      first = result.current.retryClone();
      await result.current.retryClone(); // "test again" and a finished sign-in in the same tick
    });
    await act(async () => { finish(); await first; });
    expect(probeGit).toHaveBeenCalledTimes(2);
    expect(createProject).toHaveBeenCalledTimes(1);
  });

  it('an ACCESS_ code from createProject itself also opens the panel', async () => {
    const err = Object.assign(new Error('x'), { status: 400, code: 'ACCESS_AUTH_REQUIRED', body: { kind: 'auth_required', detail: 'd', host: 'github.com', isGitHub: true } });
    const createProject = vi.fn(async () => { throw err; });
    const probeGit = vi.fn(async () => ({ reachable: true, kind: 'ok' }));
    const { result } = renderRepoScanHook({ createProject, probeGit, repo: 'https://github.com/o/r.git' });
    await act(async () => { await result.current.handleCloneTargetSubmit({ cloneDest: '/tmp/x', ephemeral: false }); });
    expect(result.current.accessFailure?.kind).toBe('auth_required');
  });

  it('a clone failure carries git detail to the step', async () => {
    const err = Object.assign(new Error('x'), { status: 502, code: 'CLONE_UNKNOWN', body: { detail: 'fatal: boom' } });
    const createProject = vi.fn(async () => { throw err; });
    const probeGit = vi.fn(async () => ({ reachable: true, kind: 'ok' }));
    const { result } = renderRepoScanHook({ createProject, probeGit, repo: 'https://github.com/o/r.git' });
    await act(async () => { await result.current.handleCloneTargetSubmit({ cloneDest: '/tmp/x', ephemeral: false }); });
    expect(result.current.cloneError).toMatch(/couldn't clone/i);
    expect(result.current.cloneDetail).toBe('fatal: boom');
  });
});
