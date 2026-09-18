import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { useStandards, STANDARD_TYPES, UNKNOWN_STANDARD_TYPE } from './useStandards.js';
import { STANDARDS_CHANGED_EVENT, STANDARDS_CHANGED_REASON } from '../../../constants.js';

function captureStandardsChanged() {
  const seen = [];
  const listener = (evt) => seen.push(evt.detail?.reason);
  window.addEventListener(STANDARDS_CHANGED_EVENT, listener);
  return { seen, stop: () => window.removeEventListener(STANDARDS_CHANGED_EVENT, listener) };
}

const fakeApi = {
  listStandards: vi.fn(),
  deleteStandard: vi.fn(),
  duplicateStandard: vi.fn(),
};

function makeWrapper() {
  const QueryWrapper = withQueryClient();
  return function Wrapper({ children }) {
    return (
      <QueryWrapper>
        <ApiProvider value={fakeApi}>{children}</ApiProvider>
      </QueryWrapper>
    );
  };
}

describe('useStandards', () => {
  beforeEach(() => {
    Object.values(fakeApi).forEach((fn) => fn.mockReset());
  });

  it('fetches standards on mount and groups them by type', async () => {
    fakeApi.listStandards.mockResolvedValue([
      { id: 'a', name: 'A', type: STANDARD_TYPES.BUILTIN },
      { id: 'b', name: 'B', type: STANDARD_TYPES.CUSTOM },
      { id: 'c', name: 'C', type: STANDARD_TYPES.CUSTOM },
    ]);
    const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(result.current.standards).toHaveLength(3);
    });
    expect(result.current.grouped[STANDARD_TYPES.BUILTIN]).toHaveLength(1);
    expect(result.current.grouped[STANDARD_TYPES.CUSTOM]).toHaveLength(2);
    expect(result.current.error).toBeNull();
  });

  it('keeps standards with an unrecognized type visible in a fallback bucket and warns once', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    try {
      fakeApi.listStandards.mockResolvedValue([
        { id: 'a', name: 'A', type: STANDARD_TYPES.BUILTIN },
        { id: 'z', name: 'Z', type: 'mystery-type' },
      ]);
      const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
      await waitFor(() => {
        expect(result.current.standards).toHaveLength(2);
      });
      expect(result.current.grouped[UNKNOWN_STANDARD_TYPE]).toHaveLength(1);
      expect(result.current.grouped[UNKNOWN_STANDARD_TYPE][0].id).toBe('z');
      expect(warnSpy).toHaveBeenCalledWith('[useStandards] unrecognized standard type:', 'mystery-type');
    } finally {
      warnSpy.mockRestore();
    }
  });

  it('exposes the error message when listStandards rejects', async () => {
    fakeApi.listStandards.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
    await waitFor(() => {
      expect(result.current.error).toBe('boom');
    });
  });

  it('handleDuplicate reports the new id once the server accepted it', async () => {
    fakeApi.listStandards.mockResolvedValue([{ id: 'a', name: 'A', type: STANDARD_TYPES.CUSTOM }]);
    fakeApi.duplicateStandard.mockResolvedValue({});
    const onDuplicated = vi.fn();
    const { result } = renderHook(() => useStandards({ onDuplicated }), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.standards).toHaveLength(1));
    await act(async () => {
      await result.current.handleDuplicate('a', 'a-copy');
    });
    expect(fakeApi.duplicateStandard).toHaveBeenCalledWith('a', 'a-copy');
    expect(onDuplicated).toHaveBeenCalledWith('a-copy');
  });

  it('handleDuplicate does not report an id when the server rejects', async () => {
    fakeApi.listStandards.mockResolvedValue([{ id: 'a', name: 'A', type: STANDARD_TYPES.CUSTOM }]);
    fakeApi.duplicateStandard.mockRejectedValue(new Error('nope'));
    const onDuplicated = vi.fn();
    const { result } = renderHook(() => useStandards({ onDuplicated }), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.standards).toHaveLength(1));
    await act(async () => {
      await result.current.handleDuplicate('a', 'a-copy');
    });
    expect(onDuplicated).not.toHaveBeenCalled();
    expect(result.current.error).toBeTruthy();
  });

  it('refresh broadcasts a list change so a mounted Evaluate picker refetches', async () => {
    fakeApi.listStandards.mockResolvedValue([]);
    const capture = captureStandardsChanged();
    try {
      const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
      await waitFor(() => expect(fakeApi.listStandards).toHaveBeenCalled());
      await act(async () => {
        await result.current.refresh();
      });
      expect(capture.seen).toEqual([STANDARDS_CHANGED_REASON.LIST]);
    } finally {
      capture.stop();
    }
  });

  it('handleDelete calls deleteStandard and refreshes', async () => {
    fakeApi.listStandards.mockResolvedValue([{ id: 'a', name: 'A', type: STANDARD_TYPES.CUSTOM }]);
    fakeApi.deleteStandard.mockResolvedValue({});
    const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.standards).toHaveLength(1));
    await act(async () => {
      await result.current.handleDelete('a');
    });
    expect(fakeApi.deleteStandard).toHaveBeenCalledWith('a');
    // refresh triggers a refetch
    expect(fakeApi.listStandards.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('handleDelete surfaces the mutation error', async () => {
    fakeApi.listStandards.mockResolvedValue([]);
    fakeApi.deleteStandard.mockRejectedValue(new Error('cannot delete'));
    const { result } = renderHook(() => useStandards(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.handleDelete('a');
    });
    expect(result.current.error).toBe('cannot delete');
  });
});
