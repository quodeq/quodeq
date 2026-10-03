import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { projectsKeys } from '../../../api/queryKeys.js';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { useAnalyzeLaunch } from './useAnalyzeLaunch.js';

const URL = 'https://github.com/acme/billing.git';
const OTHER = 'https://github.com/acme/ledger.git';
const IDLE = { state: 'idle', kind: 'clone', phase: null, percent: null, bytes: 0, repo: '', finishedAt: null };
const running = (repo = URL) => ({ state: 'running', kind: 'clone', phase: SYNC_PHASE.DOWNLOADING, percent: 45, bytes: 12582912, repo, finishedAt: null });
const done = (repo = URL, finishedAt = 1700000001000, projectId = 'p1') => ({
  ...running(repo), state: 'done', phase: SYNC_PHASE.DONE, percent: 100, projectId, scanData: { files: 3 }, finishedAt,
});
const failed = (code, detail = '', finishedAt = 1700000002000) => ({
  ...running(), state: 'error', phase: SYNC_PHASE.ERROR, code, error: 'clone failed', detail, finishedAt,
});

function fakeWizard() {
  return { state: { repo: { source: 'url', value: URL }, projectId: null }, startScan: vi.fn(), succeedScan: vi.fn(), failScan: vi.fn(), setRepo: vi.fn() };
}
function fakeForm(request = { repo: URL, source: 'url', standardIds: ['default'] }, canSubmit = true) {
  return { request: () => request, canSubmit };
}

// The hook only observes the clone slot; the test plays the app-level poller
// by writing the slot into the cache (`poll`). getCloneStatus answers with
// whatever was polled last, so an invalidation refetch changes nothing.
function setup({ registerProject = vi.fn(), probeGit = vi.fn(async () => ({ reachable: true })), slot = IDLE, form = fakeForm(), api: extra = {} } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const current = { slot };
  const api = { registerProject, probeGit, getCloneStatus: vi.fn(async () => current.slot), ...extra };
  const onLaunch = vi.fn();
  const wizard = fakeWizard();
  const hook = renderHook(() => useAnalyzeLaunch({ wizard, form, onLaunch }), {
    wrapper: ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>,
  });
  const poll = (next) => act(() => { current.slot = next; qc.setQueryData(projectsKeys.clone(), next); });
  return { ...hook, api, onLaunch, wizard, poll };
}

const accepted = () => vi.fn(async () => ({ started: true, repo: URL, dest: '/u/quodeq/repos/billing' }));
function conflict(code, extra = {}) {
  return Object.assign(new Error('refused'), { status: 409, code, body: { code, ...extra }, ...extra });
}

describe('useAnalyzeLaunch', () => {
  // The launch sends the working copy's local path: the evaluation start refuses a url.
  it('a url clones as a job and starts the evaluation exactly once when the slot reaches done', async () => {
    const getProjectInfo = vi.fn(async () => ({ path: '/u/quodeq/repos/billing' }));
    const { result, api, onLaunch, poll } = setup({ registerProject: accepted(), api: { getProjectInfo } });
    await waitFor(() => expect(api.getCloneStatus).toHaveBeenCalled());
    await act(async () => { await result.current.run(); });
    expect(api.registerProject).toHaveBeenCalledWith({ repo: URL });
    await poll(running());
    await waitFor(() => expect(result.current.phase).toBe(SYNC_PHASE.DOWNLOADING));
    expect(result.current.busy).toBe(true);
    await poll(done());
    await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
    expect(onLaunch.mock.calls[0][0]).toEqual({ projectId: 'p1', repo: '/u/quodeq/repos/billing', standardIds: ['default'] });
    await poll({ ...done() });
    expect(onLaunch).toHaveBeenCalledTimes(1);
    expect(api.registerProject).toHaveBeenCalledTimes(1);
  });

  it('sends a picked working-copy root as cloneDest', async () => {
    const form = fakeForm({ repo: URL, source: 'url', standardIds: ['default'], cloneDest: '/Volumes/work' });
    const { result, api } = setup({ registerProject: accepted(), form });
    await act(async () => { await result.current.run(); });
    expect(api.registerProject).toHaveBeenCalledWith({ repo: URL, cloneDest: '/Volumes/work' });
  });

  it('an unreachable url opens the access panel and never posts', async () => {
    const probeGit = vi.fn(async () => ({ reachable: false, kind: 'not_found', host: 'github.com', isGitHub: true }));
    const { result, api } = setup({ registerProject: accepted(), probeGit });
    await act(async () => { await result.current.run(); });
    expect(result.current.accessFailure).toMatchObject({ kind: 'not_found', host: 'github.com', isGitHub: true });
    expect(api.registerProject).not.toHaveBeenCalled();
  });

  it('a post refused by the server-side access probe opens the access panel too', async () => {
    const err = Object.assign(new Error('auth'), { status: 403, code: 'ACCESS_AUTH_REQUIRED', body: { code: 'ACCESS_AUTH_REQUIRED', kind: 'auth_required', host: 'github.com', isGitHub: true } });
    const { result } = setup({ registerProject: vi.fn(async () => { throw err; }) });
    await act(async () => { await result.current.run(); });
    expect(result.current.accessFailure).toMatchObject({ kind: 'auth_required', host: 'github.com', isGitHub: true });
    expect(result.current.startError).toBeNull();
  });

  it('a second run while one is starting is ignored', async () => {
    let release;
    const probeGit = vi.fn(() => new Promise((resolve) => { release = resolve; }));
    const { result, api } = setup({ registerProject: accepted(), probeGit });
    let first;
    act(() => { first = result.current.run(); });
    await act(async () => { await result.current.run(); });
    await act(async () => { release({ reachable: true }); await first; });
    expect(probeGit).toHaveBeenCalledTimes(1);
    expect(api.registerProject).toHaveBeenCalledTimes(1);
  });

  it('a failed clone shows the mapped message and retry posts again', async () => {
    const { result, api, onLaunch, poll } = setup({ registerProject: accepted() });
    await act(async () => { await result.current.run(); });
    await poll(running());
    await poll(failed('REPO_NOT_FOUND', 'fatal: repository not found'));
    await waitFor(() => expect(result.current.cloneError).not.toBeNull());
    expect(result.current.cloneError.message).toBe(apiErrorMessage({ code: 'REPO_NOT_FOUND', message: 'clone failed' }, 'onboarding.cloneFailed'));
    expect(result.current.cloneError.detail).toBe('fatal: repository not found');
    expect(result.current.busy).toBe(false);
    await act(async () => { await result.current.cloneError.retry(); });
    expect(api.registerProject).toHaveBeenCalledTimes(2);
    // The old error stays in the cache until the next poll; it is not shown again.
    expect(result.current.cloneError).toBeNull();
    expect(onLaunch).not.toHaveBeenCalled();
  });

  it('PROJECT_EXISTS resumes the existing project instead of failing', async () => {
    const getProjectInfo = vi.fn(async () => ({ runsCount: 0 }));
    const getProjectScan = vi.fn(async () => ({ files: 9 }));
    const { result, onLaunch, wizard, poll } = setup({ registerProject: accepted(), api: { getProjectInfo, getProjectScan } });
    await act(async () => { await result.current.run(); });
    await poll(failed('PROJECT_EXISTS', 'existing-id'));
    await waitFor(() => expect(wizard.succeedScan).toHaveBeenCalledWith('existing-id', { files: 9 }));
    await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
    expect(onLaunch).toHaveBeenCalledWith({ projectId: 'existing-id', repo: URL, standardIds: ['default'] });
    expect(result.current.cloneError).toBeNull();
  });

  it('a 409 PROJECT_EXISTS on the post resumes and launches the existing project at once', async () => {
    const registerProject = vi.fn(async () => { throw conflict('PROJECT_EXISTS', { existingProjectId: 'existing-id' }); });
    const api = { getProjectInfo: vi.fn(async () => ({ runsCount: 0, path: '/u/quodeq/repos/billing' })), getProjectScan: vi.fn(async () => ({})) };
    const { result, onLaunch, wizard } = setup({ registerProject, api });
    await act(async () => { await result.current.run(); });
    expect(wizard.succeedScan).toHaveBeenCalledWith('existing-id', {});
    expect(onLaunch).toHaveBeenCalledTimes(1);
    expect(onLaunch).toHaveBeenCalledWith({ projectId: 'existing-id', repo: '/u/quodeq/repos/billing', standardIds: ['default'] });
    expect(result.current.startError).toBeNull();
  });

  it('a 409 CLONE_IN_PROGRESS attaches to the running slot and shows no toast', async () => {
    const registerProject = vi.fn(async () => { throw conflict('CLONE_IN_PROGRESS'); });
    const { result, onLaunch, poll } = setup({ registerProject, slot: running() });
    await act(async () => { await result.current.run(); });
    expect(result.current.startError).toBeNull();
    expect(result.current.attachedElsewhere).toBe(true);
    expect(result.current.slot).toMatchObject({ repo: URL, phase: SYNC_PHASE.DOWNLOADING });
    expect(result.current.busy).toBe(true);
    await poll(done());
    await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
  });

  it('a 409 for another repository waits for it, then clones this one', async () => {
    const registerProject = vi.fn()
      .mockRejectedValueOnce(conflict('CLONE_IN_PROGRESS'))
      .mockResolvedValueOnce({ started: true, repo: URL, dest: '/u/quodeq/repos/billing' });
    const { result, onLaunch, poll } = setup({ registerProject, slot: running(OTHER) });
    await act(async () => { await result.current.run(); });
    expect(result.current.slot).toMatchObject({ repo: OTHER });
    await poll(done(OTHER, 1700000005000, 'other'));
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(2));
    expect(onLaunch).not.toHaveBeenCalled();
    await poll(running());
    await poll(done(URL, 1700000006000, 'mine'));
    await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
    // No project to read here (getProjectInfo fails): the repo goes as it is.
    expect(onLaunch.mock.calls[0][0]).toMatchObject({ projectId: 'mine', repo: URL });
  });

  it('a folder registers synchronously and launches at once', async () => {
    const registerProject = vi.fn(async () => ({ projectId: 'p2', scanData: {} }));
    const form = fakeForm({ repo: '/Users/me/app', source: 'folder', standardIds: ['default'] });
    const { result, api, onLaunch, wizard } = setup({ registerProject, form });
    await waitFor(() => expect(api.getCloneStatus).toHaveBeenCalledTimes(1));
    await act(async () => { await result.current.run(); });
    expect(api.registerProject).toHaveBeenCalledWith({ repo: '/Users/me/app' });
    expect(wizard.startScan).toHaveBeenCalledTimes(1);
    expect(wizard.succeedScan).toHaveBeenCalledWith('p2', {});
    expect(onLaunch).toHaveBeenCalledTimes(1);
    expect(onLaunch.mock.calls[0][0]).toMatchObject({ projectId: 'p2' });
    expect(api.getCloneStatus).toHaveBeenCalledTimes(1);
  });

  it('a refused folder shows the mapped message', async () => {
    const err = Object.assign(new Error('nope'), { status: 400, code: 'NOT_DIR', body: { code: 'NOT_DIR' } });
    const form = fakeForm({ repo: '/nope', source: 'folder', standardIds: ['default'] });
    const { result, onLaunch } = setup({ registerProject: vi.fn(async () => { throw err; }), form });
    await act(async () => { await result.current.run(); });
    expect(result.current.startError.message).toBe(apiErrorMessage(err, 'onboarding.scanFailed'));
    expect(onLaunch).not.toHaveBeenCalled();
  });

  // Review Focus 1: closing the panel cancels nothing and starts nothing later.
  it('unmounting after the 202 never launches when the clone lands', async () => {
    const { result, onLaunch, unmount, poll } = setup({ registerProject: accepted() });
    await act(async () => { await result.current.run(); });
    unmount();
    await poll(done());
    expect(onLaunch).not.toHaveBeenCalled();
  });

  // Review Focus 2: the DONE edge is keyed by repo and by a new finishedAt.
  it('a stale done, of another repo or from before the post, never launches', async () => {
    const { result, api, onLaunch, poll } = setup({ registerProject: accepted(), slot: done(URL, 1600000000000, 'old') });
    await waitFor(() => expect(api.getCloneStatus).toHaveBeenCalled());
    await poll(done(URL, 1600000000000, 'old'));
    await act(async () => { await result.current.run(); });
    await poll({ ...done(URL, 1600000000000, 'old') });
    await poll(done(OTHER, 1700000009000, 'other'));
    expect(onLaunch).not.toHaveBeenCalled();
    await poll(done(URL, 1700000010000, 'fresh'));
    await waitFor(() => expect(onLaunch).toHaveBeenCalledWith(expect.objectContaining({ projectId: 'fresh' })));
  });

  // Review Focus 3: reopening the panel while a clone runs attaches to it.
  it('reopening while a clone runs attaches, is busy and launches when it lands', async () => {
    const { result, api, onLaunch, poll } = setup({ registerProject: accepted(), slot: running() });
    await waitFor(() => expect(result.current.slot).toMatchObject({ repo: URL }));
    expect(result.current.busy).toBe(true);
    expect(result.current.attachedElsewhere).toBe(false);
    await poll(done());
    await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
    expect(api.registerProject).not.toHaveBeenCalled();
  });
  it('an attached clone landing while the form cannot submit (no model) shows the project, never launches', async () => {
    const { result, onLaunch, wizard, poll } = setup({ slot: running(), form: fakeForm(undefined, false) });
    await waitFor(() => expect(result.current.busy).toBe(true));
    await poll(done());
    await waitFor(() => expect(wizard.succeedScan).toHaveBeenCalledWith('p1', { files: 3 }));
    expect({ launches: onLaunch.mock.calls.length, busy: result.current.busy }).toEqual({ launches: 0, busy: false });
  });
  // An unmounted panel never launches, even after a slow await.
  it('a folder registration that resolves after the panel closed never launches', async () => {
    let resolve;
    const registerProject = vi.fn(() => new Promise((r) => { resolve = r; }));
    const form = fakeForm({ repo: '/Users/me/app', source: 'folder', standardIds: ['default'] });
    const { result, onLaunch, unmount } = setup({ registerProject, form });
    let pendingRun;
    act(() => { pendingRun = result.current.run(); });
    unmount();
    await act(async () => { resolve({ projectId: 'p2', scanData: {} }); await pendingRun; });
    expect(onLaunch).not.toHaveBeenCalled();
  });

  it('a PROJECT_EXISTS resume that finishes after the panel closed never launches', async () => {
    let resolveScan;
    const api = { getProjectInfo: vi.fn(async () => ({ runsCount: 0 })), getProjectScan: vi.fn(() => new Promise((r) => { resolveScan = r; })) };
    const { result, onLaunch, unmount, poll } = setup({ registerProject: accepted(), api });
    await act(async () => { await result.current.run(); });
    await poll(failed('PROJECT_EXISTS', 'existing-id'));
    await waitFor(() => expect(api.getProjectScan).toHaveBeenCalled());
    unmount();
    await act(async () => { resolveScan({}); });
    expect(onLaunch).not.toHaveBeenCalled();
  });

  it('an attached launch sends the slot repo even if the field was edited', async () => {
    const request = { repo: URL, source: 'url', standardIds: ['default'] };
    const { result, onLaunch, poll } = setup({ registerProject: accepted(), slot: running(), form: { request: () => request, canSubmit: true } });
    await waitFor(() => expect(result.current.busy).toBe(true));
    request.repo = OTHER;
    await poll(done());
    await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
    expect(onLaunch.mock.calls[0][0]).toMatchObject({ projectId: 'p1', repo: URL });
  });
  it('a followed clone that vanishes (slot back to idle) ends with an error', async () => {
    const { result, onLaunch, poll } = setup({ registerProject: accepted() });
    await act(async () => { await result.current.run(); });
    await poll(running());
    await waitFor(() => expect(result.current.slot).not.toBeNull());
    await poll({ ...IDLE });
    await waitFor(() => expect(result.current.startError?.message).toBe('could not clone the repository'));
    expect(result.current.busy).toBe(false);
    expect(onLaunch).not.toHaveBeenCalled();
  });
  it('a failed status read after a 409 follows this repo, not the cached one', async () => {
    const registerProject = vi.fn(async () => { throw conflict('CLONE_IN_PROGRESS'); });
    const { result, api, onLaunch, poll } = setup({ registerProject, slot: done(OTHER, 1600000000000, 'old') });
    await waitFor(() => expect(api.getCloneStatus).toHaveBeenCalled());
    api.getCloneStatus.mockRejectedValueOnce(new Error('down'));
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    await act(async () => { await result.current.run(); });
    expect(result.current.attachedElsewhere).toBe(true);
    await poll(running());
    await poll(done());
    await waitFor(() => expect(onLaunch).toHaveBeenCalledTimes(1));
    expect(onLaunch.mock.calls[0][0]).toMatchObject({ projectId: 'p1', repo: URL });
    warn.mockRestore();
  });

  it('a PROJECT_EXISTS that cannot be resumed shows no project id as git output', async () => {
    const api = { getProjectInfo: vi.fn(async () => ({ runsCount: 3 })), getProjectScan: vi.fn() };
    const { result, poll } = setup({ registerProject: accepted(), api });
    await act(async () => { await result.current.run(); });
    await poll(failed('PROJECT_EXISTS', 'existing-id'));
    await waitFor(() => expect(result.current.cloneError).not.toBeNull());
    expect(result.current.cloneError.detail).toBe('');
  });
});
