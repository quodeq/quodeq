import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useImportFlow, STEP } from './useImportFlow.js';

function wrapper(api) {
  return function Wrapper({ children }) {
    return <ApiProvider value={api}>{children}</ApiProvider>;
  };
}

function fakeFileEvent({ size = 10, text = '{"id":"my-standard"}' } = {}) {
  return { target: { files: [{ size, text: async () => text }] } };
}

describe('useImportFlow', () => {
  it('success: onImported is called with the server-echoed id', async () => {
    const importStandard = vi.fn().mockResolvedValue({ detail: { id: 'stored-id' } });
    const onImported = vi.fn();
    const { result } = renderHook(() => useImportFlow(onImported), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent()); });

    expect(importStandard).toHaveBeenCalledWith({ id: 'my-standard' }, false);
    expect(onImported).toHaveBeenCalledWith('stored-id');
  });

  it('success: falls back to the parsed file id when detail.id is absent', async () => {
    const importStandard = vi.fn().mockResolvedValue({});
    const onImported = vi.fn();
    const { result } = renderHook(() => useImportFlow(onImported), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent()); });

    expect(onImported).toHaveBeenCalledWith('my-standard');
  });

  it('conflict: stops at STEP.CONFLICT with the existing standard and warnings', async () => {
    const importStandard = vi.fn().mockResolvedValue({ _conflict: true, existing: { id: 'my-standard', name: 'Existing' }, warnings: ['dupe'] });
    const onImported = vi.fn();
    const { result } = renderHook(() => useImportFlow(onImported), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent()); });

    expect(result.current.step).toBe(STEP.CONFLICT);
    expect(result.current.conflict).toEqual({ id: 'my-standard', name: 'Existing' });
    expect(result.current.warnings).toEqual(['dupe']);
    expect(onImported).not.toHaveBeenCalled();
  });

  it('conflict -> overwrite: handleImportAnyway re-calls importStandard with force=true', async () => {
    const importStandard = vi.fn()
      .mockResolvedValueOnce({ _conflict: true, existing: { id: 'my-standard' }, warnings: [] })
      .mockResolvedValueOnce({ detail: { id: 'my-standard' } });
    const onImported = vi.fn();
    const { result } = renderHook(() => useImportFlow(onImported), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent()); });
    await act(async () => { await result.current.handleImportAnyway(); });

    expect(importStandard).toHaveBeenLastCalledWith({ id: 'my-standard' }, true);
    expect(onImported).toHaveBeenCalledWith('my-standard');
  });

  it('conflict -> import as copy: reissues with an "-imported" id suffix, force=false', async () => {
    const importStandard = vi.fn()
      .mockResolvedValueOnce({ _conflict: true, existing: { id: 'my-standard' }, warnings: [] })
      .mockResolvedValueOnce({ detail: { id: 'my-standard-imported' } });
    const onImported = vi.fn();
    const { result } = renderHook(() => useImportFlow(onImported), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent()); });
    await act(async () => { await result.current.handleImportAsCopy(); });

    expect(importStandard).toHaveBeenLastCalledWith({ id: 'my-standard-imported' }, false);
    expect(onImported).toHaveBeenCalledWith('my-standard-imported');
  });

  it('warnings without force: stops at STEP.WARNINGS', async () => {
    const importStandard = vi.fn().mockResolvedValue({ warnings: ['heads up'] });
    const onImported = vi.fn();
    const { result } = renderHook(() => useImportFlow(onImported), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent()); });

    expect(result.current.step).toBe(STEP.WARNINGS);
    expect(result.current.warnings).toEqual(['heads up']);
    expect(onImported).not.toHaveBeenCalled();
  });

  it('warnings -> import anyway: force=true completes the import', async () => {
    const importStandard = vi.fn()
      .mockResolvedValueOnce({ warnings: ['heads up'] })
      .mockResolvedValueOnce({ detail: { id: 'my-standard' } });
    const onImported = vi.fn();
    const { result } = renderHook(() => useImportFlow(onImported), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent()); });
    await act(async () => { await result.current.handleImportAnyway(); });

    expect(importStandard).toHaveBeenLastCalledWith({ id: 'my-standard' }, true);
    expect(onImported).toHaveBeenCalledWith('my-standard');
  });

  it('API error: STEP.ERROR with a translated message, onImported not called', async () => {
    const importStandard = vi.fn().mockRejectedValue(Object.assign(new Error('boom'), { code: 'SOME_CODE' }));
    const onImported = vi.fn();
    const { result } = renderHook(() => useImportFlow(onImported), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent()); });

    expect(result.current.step).toBe(STEP.ERROR);
    expect(typeof result.current.error).toBe('string');
    expect(onImported).not.toHaveBeenCalled();
  });

  it('oversized file: STEP.ERROR without calling importStandard', async () => {
    const importStandard = vi.fn();
    const { result } = renderHook(() => useImportFlow(vi.fn()), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent({ size: 2 * 1024 * 1024 })); });

    expect(result.current.step).toBe(STEP.ERROR);
    expect(result.current.error).toContain('too large');
    expect(importStandard).not.toHaveBeenCalled();
  });

  it('unparsable JSON: STEP.ERROR without calling importStandard', async () => {
    const importStandard = vi.fn();
    const { result } = renderHook(() => useImportFlow(vi.fn()), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile(fakeFileEvent({ text: 'not json' })); });

    expect(result.current.step).toBe(STEP.ERROR);
    expect(importStandard).not.toHaveBeenCalled();
  });

  it('no file picked: handleFile is a no-op', async () => {
    const importStandard = vi.fn();
    const { result } = renderHook(() => useImportFlow(vi.fn()), { wrapper: wrapper({ importStandard }) });

    await act(async () => { await result.current.handleFile({ target: { files: [] } }); });

    expect(result.current.step).toBe(STEP.PICK);
    expect(importStandard).not.toHaveBeenCalled();
  });
});
