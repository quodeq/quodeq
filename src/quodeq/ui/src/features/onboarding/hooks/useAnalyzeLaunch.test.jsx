import { describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { projectsKeys } from '../../../api/queryKeys.js';
import { apiErrorMessage } from '../../../strings/apiErrors.js';
import { useAnalyzeLaunch } from './useAnalyzeLaunch.js';

const URL = 'https://github.com/acme/billing.git';
const FOLDER = '/Users/me/code/app';

function fakeWizard() {
  return { state: { repo: { source: 'url', value: URL }, projectId: null }, startScan: vi.fn(), succeedScan: vi.fn(), failScan: vi.fn(), setRepo: vi.fn() };
}
const urlForm = (extra = {}) => ({ request: () => ({ repo: URL, source: 'url', ...extra }) });
const folderForm = () => ({ request: () => ({ repo: FOLDER, source: 'folder' }) });

function setup({ registerProject = vi.fn(), probeGit = vi.fn(async () => ({ reachable: true })), form = urlForm(), api: extra = {} } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const api = { registerProject, probeGit, getCloneStatus: vi.fn(async () => null), ...extra };
  const onAdded = vi.fn();
  const wizard = fakeWizard();
  const hook = renderHook(() => useAnalyzeLaunch({ wizard, form, onAdded }), {
    wrapper: ({ children }) => <QueryClientProvider client={qc}><ApiProvider value={api}>{children}</ApiProvider></QueryClientProvider>,
  });
  return { ...hook, api, onAdded, wizard, qc };
}

const accepted = () => vi.fn(async () => ({ started: true, repo: URL, dest: '/u/quodeq/repos/billing' }));
function conflict(code, extra = {}) {
  return Object.assign(new Error('refused'), { status: 409, code, body: { code, ...extra }, ...extra });
}

describe('useAnalyzeLaunch', () => {
  it('a url probes, posts the clone job and hands over as cloning', async () => {
    const { result, api, onAdded, qc } = setup({ registerProject: accepted() });
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    await act(async () => { await result.current.run(); });
    expect(api.probeGit).toHaveBeenCalledWith(URL);
    expect(api.registerProject).toHaveBeenCalledWith({ repo: URL });
    expect(onAdded).toHaveBeenCalledWith({ projectId: null, cloning: true });
    // The app-level poller is woken so the tile shows at once.
    expect(invalidate).toHaveBeenCalledWith({ queryKey: projectsKeys.clone() });
    expect(result.current.busy).toBe(false);
  });

  it('sends a picked working-copy root as cloneDest', async () => {
    const { result, api } = setup({ registerProject: accepted(), form: urlForm({ cloneDest: '/Volumes/work' }) });
    await act(async () => { await result.current.run(); });
    expect(api.registerProject).toHaveBeenCalledWith({ repo: URL, cloneDest: '/Volumes/work' });
  });

  it('an unreachable url opens the access panel and never posts', async () => {
    const { result, api, onAdded } = setup({ probeGit: vi.fn(async () => ({ reachable: false, kind: 'auth_required', host: 'github.com', isGitHub: true })) });
    await act(async () => { await result.current.run(); });
    expect(api.registerProject).not.toHaveBeenCalled();
    expect(onAdded).not.toHaveBeenCalled();
    expect(result.current.accessFailure).toMatchObject({ kind: 'auth_required', host: 'github.com', isGitHub: true });
  });

  it('a second run while one is starting is ignored', async () => {
    let release;
    const registerProject = vi.fn(() => new Promise((resolve) => { release = () => resolve({ started: true, repo: URL }); }));
    const { result, api } = setup({ registerProject });
    let first;
    act(() => { first = result.current.run(); });
    await waitFor(() => expect(result.current.busy).toBe(true));
    await act(async () => { await result.current.run(); });
    expect(api.registerProject).toHaveBeenCalledTimes(1);
    await act(async () => { release(); await first; });
    expect(result.current.busy).toBe(false);
  });

  it('a refused clone start shows the mapped message with retry, and retry posts again', async () => {
    const err = Object.assign(new Error('bad'), { status: 400, code: 'DEST_EXISTS', detail: 'folder exists' });
    const registerProject = vi.fn().mockRejectedValueOnce(err).mockResolvedValueOnce({ started: true, repo: URL });
    const { result, api, onAdded } = setup({ registerProject });
    await act(async () => { await result.current.run(); });
    expect(result.current.startError.message).toBe(apiErrorMessage(err, 'onboarding.cloneFailed'));
    expect(onAdded).not.toHaveBeenCalled();
    await act(async () => { await result.current.startError.retry(); });
    expect(api.registerProject).toHaveBeenCalledTimes(2);
    expect(onAdded).toHaveBeenCalledWith({ projectId: null, cloning: true });
    expect(result.current.startError).toBeNull();
  });

  it('a 409 PROJECT_EXISTS resumes the registered project and hands it over', async () => {
    const registerProject = vi.fn().mockRejectedValue(conflict('PROJECT_EXISTS', { existingProjectId: 'p-old' }));
    const getProjectInfo = vi.fn(async () => ({ id: 'p-old', runsCount: 0 }));
    const getProjectScan = vi.fn(async () => ({ total_files: 3 }));
    const { result, onAdded, wizard } = setup({ registerProject, api: { getProjectInfo, getProjectScan } });
    await act(async () => { await result.current.run(); });
    expect(wizard.succeedScan).toHaveBeenCalledWith('p-old', { total_files: 3 });
    expect(onAdded).toHaveBeenCalledWith({ projectId: 'p-old', cloning: false });
    expect(result.current.startError).toBeNull();
  });

  it('a 409 CLONE_IN_PROGRESS says a clone is already running and keeps the panel', async () => {
    const registerProject = vi.fn().mockRejectedValue(conflict('CLONE_IN_PROGRESS'));
    const { result, onAdded } = setup({ registerProject });
    await act(async () => { await result.current.run(); });
    expect(onAdded).not.toHaveBeenCalled();
    expect(result.current.startError.message).toBe('a clone is already running. wait for it to finish, then add again.');
  });

  it('a folder registers synchronously, never probes, and hands the project over', async () => {
    const registerProject = vi.fn(async () => ({ projectId: 'p-folder', scanData: { total_files: 9 } }));
    const { result, api, onAdded, wizard } = setup({ registerProject, form: folderForm() });
    await act(async () => { await result.current.run(); });
    expect(api.probeGit).not.toHaveBeenCalled();
    expect(api.registerProject).toHaveBeenCalledWith({ repo: FOLDER });
    expect(wizard.startScan).toHaveBeenCalledTimes(1);
    expect(wizard.succeedScan).toHaveBeenCalledWith('p-folder', { total_files: 9 });
    expect(onAdded).toHaveBeenCalledWith({ projectId: 'p-folder', cloning: false });
  });

  it('a refused folder shows the mapped message and marks the scan failed', async () => {
    const err = Object.assign(new Error('nope'), { status: 400, code: 'NOT_DIR' });
    const { result, onAdded, wizard } = setup({ registerProject: vi.fn().mockRejectedValue(err), form: folderForm() });
    await act(async () => { await result.current.run(); });
    expect(result.current.startError.message).toBe(apiErrorMessage(err, 'onboarding.scanFailed'));
    expect(wizard.failScan).toHaveBeenCalledWith(expect.objectContaining({ code: 'NOT_DIR' }));
    expect(onAdded).not.toHaveBeenCalled();
  });

  it('a registration that resolves after the panel closed hands nothing over', async () => {
    let release;
    const registerProject = vi.fn(() => new Promise((resolve) => { release = () => resolve({ projectId: 'p-late', scanData: {} }); }));
    const { result, onAdded, unmount } = setup({ registerProject, form: folderForm() });
    let pending;
    act(() => { pending = result.current.run(); });
    unmount();
    await act(async () => { release(); await pending; });
    expect(onAdded).not.toHaveBeenCalled();
  });
});
