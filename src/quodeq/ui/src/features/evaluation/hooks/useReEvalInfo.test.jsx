import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useReEvalInfo } from './useReEvalInfo.js';

/**
 * Cluster 18 (frontend silent-catch / status-conflation): a fetch failure
 * here used to be either surfaced only when there was no initialInfo
 * fallback, or -- on a later refresh/explicit retry() with a fallback
 * present -- completely silent (no error state, no console trace).
 */

describe('useReEvalInfo', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sets info null and a visible error when there is no initialInfo fallback', async () => {
    const getProjectInfo = vi.fn().mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() =>
      useReEvalInfo('proj-1', null, { getProjectInfo, relocateProject: vi.fn() }),
    );

    await waitFor(() => expect(result.current.error).toBe('boom'));
    expect(result.current.info).toBeNull();
  });

  it('logs the real error to console even when initialInfo keeps the UI silent', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const err = new Error('server exploded');
    const getProjectInfo = vi.fn().mockRejectedValue(err);
    const fallbackInfo = { name: 'demo', path: '/repos/demo', location: 'local' };

    const { result } = renderHook(() =>
      useReEvalInfo('proj-2', fallbackInfo, { getProjectInfo, relocateProject: vi.fn() }),
    );

    await waitFor(() => expect(getProjectInfo).toHaveBeenCalled());
    await waitFor(() => {
      expect(errorSpy).toHaveBeenCalledWith(expect.stringMatching(/project info/i), err);
    });

    // Legitimate-empty-state discipline: a fallback already exists, so the
    // failed refresh must not blank it out or flip on the error screen.
    expect(result.current.info).toBe(fallbackInfo);
    expect(result.current.error).toBeNull();
  });

  it('a failed explicit retry() is traced even though a fallback keeps the view unchanged', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const fallbackInfo = { name: 'demo', path: '/repos/demo', location: 'local' };
    const getProjectInfo = vi.fn()
      .mockRejectedValueOnce(new Error('initial load failed'))
      .mockRejectedValueOnce(new Error('retry failed too'));

    const { result } = renderHook(() =>
      useReEvalInfo('proj-3', fallbackInfo, { getProjectInfo, relocateProject: vi.fn() }),
    );

    await waitFor(() => expect(getProjectInfo).toHaveBeenCalledTimes(1));
    await waitFor(() => {
      expect(errorSpy).toHaveBeenCalledWith(expect.stringMatching(/project info/i), expect.any(Error));
    });
    errorSpy.mockClear();

    act(() => result.current.retry());

    await waitFor(() => expect(getProjectInfo).toHaveBeenCalledTimes(2));
    await waitFor(() => {
      expect(errorSpy).toHaveBeenCalledWith(
        expect.stringMatching(/project info/i),
        expect.objectContaining({ message: 'retry failed too' }),
      );
    });
    // Still no error screen / no wiped-out info: the fallback stands.
    expect(result.current.info).toBe(fallbackInfo);
    expect(result.current.error).toBeNull();
  });

  it('recovers from an error state once a retry succeeds', async () => {
    const goodInfo = { name: 'demo', path: '/repos/demo', location: 'local' };
    const getProjectInfo = vi.fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(goodInfo);

    const { result } = renderHook(() =>
      useReEvalInfo('proj-4', null, { getProjectInfo, relocateProject: vi.fn() }),
    );

    await waitFor(() => expect(result.current.error).toBe('boom'));

    act(() => result.current.retry());

    await waitFor(() => expect(result.current.info).toEqual(goodInfo));
    expect(result.current.error).toBeNull();
  });
});
