import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ApiProvider } from '../api/ApiContext.jsx';
import { useProjectActions } from './useProjectActions.js';

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

    it('falls back to alert() with the rendered message when no onError is supplied', async () => {
      const err = new Error('disk full');
      const fakeApi = { deleteProject: vi.fn().mockRejectedValue(err) };
      const { result } = renderActions(fakeApi); // no options -> default onError

      await act(async () => { await result.current.handleDeleteProject('a'); });

      expect(alertSpy).toHaveBeenCalledTimes(1);
      expect(alertSpy.mock.calls[0][0]).toContain('disk full');
    });
  });
});
