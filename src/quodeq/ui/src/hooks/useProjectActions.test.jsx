import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ApiProvider } from '../api/ApiContext.jsx';
import { useProjectActions, makeHandleDeleteProject } from './useProjectActions.js';
import { apiErrorMessage } from '../strings/apiErrors.js';

const PROJECTS = [{ id: 'a', name: 'Alpha' }, { id: 'b', name: 'Beta' }];

function renderActions(fakeApi, options) {
  const handleProjectChange = vi.fn();
  const loadProjects = vi.fn();
  const { result } = renderHook(
    () => useProjectActions(
      { projects: PROJECTS, selectedProject: 'a', handleProjectChange, loadProjects },
      options,
    ),
    { wrapper: ({ children }) => <ApiProvider value={fakeApi}>{children}</ApiProvider> },
  );
  return { result, handleProjectChange, loadProjects };
}

describe('useProjectActions', () => {
  describe('handleDeleteProject', () => {
    it('returns { ok: true } and reloads projects on success', async () => {
      const fakeApi = { deleteProject: vi.fn().mockResolvedValue(undefined) };
      const { result, loadProjects } = renderActions(fakeApi);

      let outcome;
      await act(async () => { outcome = await result.current.handleDeleteProject('a'); });

      expect(outcome).toEqual({ ok: true });
      expect(loadProjects).toHaveBeenCalledTimes(1);
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
      const { result, loadProjects } = renderActions(fakeApi, { onError });

      let outcome;
      await act(async () => { outcome = await result.current.handleDeleteProject('a'); });

      expect(outcome).toEqual({
        ok: false, messageKey: 'projects.deleteProjectFailed', vars: { error: 'disk full' },
      });
      expect(onError).toHaveBeenCalledWith('projects.deleteProjectFailed', { error: 'disk full' });
      expect(loadProjects).not.toHaveBeenCalled();
    });

    it('delete failure message is mapped through apiErrorMessage', async () => {
      // FORBIDDEN is a mapped code, so its friendly text diverges from the
      // raw backend message -- that divergence is what makes this test fail
      // against the old `error: err.message` code.
      const err = Object.assign(new Error('raw backend text'), { code: 'FORBIDDEN' });
      const deleteProject = vi.fn().mockRejectedValue(err);
      const fail = vi.fn((key, params) => ({ ok: false, key, params }));
      const handler = makeHandleDeleteProject({
        deleteProject, projects: [], selectedProject: null, handleProjectChange: vi.fn(), loadProjects: vi.fn(), fail,
      });

      await handler('p1');

      expect(fail).toHaveBeenCalledWith('projects.deleteProjectFailed', { error: apiErrorMessage(err, 'projects.deleteProjectFailed') });
      expect(fail.mock.calls[0][1].error).not.toBe(err.message);
    });
  });

  describe('handleRelocateProject', () => {
    it('returns { ok: true } and reloads projects on success', async () => {
      const fakeApi = { relocateProject: vi.fn().mockResolvedValue(undefined) };
      const { result, loadProjects } = renderActions(fakeApi);

      let outcome;
      await act(async () => { outcome = await result.current.handleRelocateProject('a', '/new/path'); });

      expect(outcome).toEqual({ ok: true });
      expect(loadProjects).toHaveBeenCalledTimes(1);
    });

    it('returns a failure result and calls onError on failure, without reloading', async () => {
      const err = new Error('path not found');
      const fakeApi = { relocateProject: vi.fn().mockRejectedValue(err) };
      const onError = vi.fn();
      const { result, loadProjects } = renderActions(fakeApi, { onError });

      let outcome;
      await act(async () => { outcome = await result.current.handleRelocateProject('a', '/bad/path'); });

      expect(outcome).toEqual({
        ok: false, messageKey: 'projects.relocateFailed', vars: { error: 'path not found' },
      });
      expect(onError).toHaveBeenCalledWith('projects.relocateFailed', { error: 'path not found' });
      expect(loadProjects).not.toHaveBeenCalled();
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
