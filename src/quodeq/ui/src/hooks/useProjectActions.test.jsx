import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiProvider } from '../api/ApiContext.jsx';
import { projectsKeys } from '../api/queryKeys.js';
import { useProjectActions, makeHandleDeleteProject } from './useProjectActions.js';
import { apiErrorMessage } from '../strings/apiErrors.js';

const PROJECTS = [{ id: 'a', name: 'Alpha' }, { id: 'b', name: 'Beta' }];

// Every successful mutation must refetch the shared project list; the spy
// on the client's invalidateQueries is how these tests observe that.
function renderActions(fakeApi, options) {
  const handleProjectChange = vi.fn();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const { result } = renderHook(
    () => useProjectActions(
      { projects: PROJECTS, selectedProject: 'a', handleProjectChange },
      options,
    ),
    {
      wrapper: ({ children }) => (
        <QueryClientProvider client={queryClient}><ApiProvider value={fakeApi}>{children}</ApiProvider></QueryClientProvider>
      ),
    },
  );
  const projectsInvalidations = () => invalidate.mock.calls.filter(([arg]) => (
    JSON.stringify(arg?.queryKey) === JSON.stringify(projectsKeys.list())
  )).length;
  return { result, handleProjectChange, projectsInvalidations };
}

// Stands in for the native file picker: the hidden input's click() selects
// *file* and fires the change event pickImportFile waits on.
function pickFileOnClick(file) {
  return vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(function pick() {
    Object.defineProperty(this, 'files', { value: [file] });
    this.dispatchEvent(new Event('change'));
  });
}

describe('useProjectActions', () => {
  describe('handleDeleteProject', () => {
    it('returns { ok: true } and reloads projects on success', async () => {
      const fakeApi = { deleteProject: vi.fn().mockResolvedValue(undefined) };
      const { result, projectsInvalidations } = renderActions(fakeApi);

      let outcome;
      await act(async () => { outcome = await result.current.handleDeleteProject('a'); });

      expect(outcome).toEqual({ ok: true });
      expect(projectsInvalidations()).toBe(1);
    });

    it('moves the selection when the deleted project was selected', async () => {
      const fakeApi = { deleteProject: vi.fn().mockResolvedValue(undefined) };
      const { result, handleProjectChange } = renderActions(fakeApi);

      await act(async () => { await result.current.handleDeleteProject('a'); });

      expect(handleProjectChange).toHaveBeenCalledWith('b');
    });

    it('returns { ok: false, messageKey, vars } on failure and calls onError with them', async () => {
      const err = new Error('disk full');
      const fakeApi = { deleteProject: vi.fn().mockRejectedValue(err) };
      const onError = vi.fn();
      const { result, projectsInvalidations } = renderActions(fakeApi, { onError });

      let outcome;
      await act(async () => { outcome = await result.current.handleDeleteProject('a'); });

      expect(outcome).toEqual({
        ok: false, messageKey: 'projects.deleteProjectFailed', vars: { error: 'disk full' },
      });
      expect(onError).toHaveBeenCalledWith('projects.deleteProjectFailed', { error: 'disk full' });
      expect(projectsInvalidations()).toBe(0);
    });

    it('delete failure message is mapped through apiErrorMessage', async () => {
      // FORBIDDEN is a mapped code, so its friendly text diverges from the
      // raw backend message -- that divergence is what makes this test fail
      // against the old `error: err.message` code.
      const err = Object.assign(new Error('raw backend text'), { code: 'FORBIDDEN' });
      const deleteProject = vi.fn().mockRejectedValue(err);
      const fail = vi.fn((key, params) => ({ ok: false, key, params }));
      const handler = makeHandleDeleteProject({
        deleteProject, projects: [], selectedProject: null, handleProjectChange: vi.fn(), refreshProjects: vi.fn(), fail,
      });

      await handler('p1');

      expect(fail).toHaveBeenCalledWith('projects.deleteProjectFailed', { error: apiErrorMessage(err, 'projects.deleteProjectFailed') });
      expect(fail.mock.calls[0][1].error).not.toBe(err.message);
    });
  });

  describe('handleRelocateProject', () => {
    it('returns { ok: true } and reloads projects on success', async () => {
      const fakeApi = { relocateProject: vi.fn().mockResolvedValue(undefined) };
      const { result, projectsInvalidations } = renderActions(fakeApi);

      let outcome;
      await act(async () => { outcome = await result.current.handleRelocateProject('a', '/new/path'); });

      expect(outcome).toEqual({ ok: true });
      expect(projectsInvalidations()).toBe(1);
    });

    it('returns a failure result and calls onError on failure, without reloading', async () => {
      const err = new Error('path not found');
      const fakeApi = { relocateProject: vi.fn().mockRejectedValue(err) };
      const onError = vi.fn();
      const { result, projectsInvalidations } = renderActions(fakeApi, { onError });

      let outcome;
      await act(async () => { outcome = await result.current.handleRelocateProject('a', '/bad/path'); });

      expect(outcome).toEqual({
        ok: false, messageKey: 'projects.relocateFailed', vars: { error: 'path not found' },
      });
      expect(onError).toHaveBeenCalledWith('projects.relocateFailed', { error: 'path not found' });
      expect(projectsInvalidations()).toBe(0);
    });
  });

  describe('handleImportProject', () => {
    afterEach(() => { vi.restoreAllMocks(); });

    it('refetches the project list after a successful import', async () => {
      pickFileOnClick(new File(['zip'], 'p.zip'));
      const fakeApi = { importProject: vi.fn().mockResolvedValue({ projectId: 'c' }) };
      const { result, projectsInvalidations } = renderActions(fakeApi);

      let outcome;
      await act(async () => { outcome = await result.current.handleImportProject(); });

      expect(outcome).toEqual({ ok: true });
      expect(fakeApi.importProject).toHaveBeenCalledTimes(1);
      expect(projectsInvalidations()).toBe(1);
    });

    it('does not refetch when the import fails', async () => {
      pickFileOnClick(new File(['zip'], 'p.zip'));
      const fakeApi = { importProject: vi.fn().mockRejectedValue(new Error('bad zip')) };
      const { result, projectsInvalidations } = renderActions(fakeApi, { onError: vi.fn() });

      let outcome;
      await act(async () => { outcome = await result.current.handleImportProject(); });

      expect(outcome.ok).toBe(false);
      expect(projectsInvalidations()).toBe(0);
    });
  });

  describe('default onError', () => {
    let alertSpy;
    beforeEach(() => { alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {}); });
    afterEach(() => { alertSpy.mockRestore(); });

    it('is a no-op when no onError is supplied: no alert(), failure still surfaces structurally', async () => {
      const err = new Error('disk full');
      const fakeApi = { deleteProject: vi.fn().mockRejectedValue(err) };
      const { result } = renderActions(fakeApi); // no options -> default onError

      let outcome;
      await act(async () => { outcome = await result.current.handleDeleteProject('a'); });

      expect(outcome).toEqual({
        ok: false, messageKey: 'projects.deleteProjectFailed', vars: { error: 'disk full' },
      });
      expect(alertSpy).not.toHaveBeenCalled();
    });
  });
});
