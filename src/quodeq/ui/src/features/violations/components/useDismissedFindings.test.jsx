import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDismissedFindings } from './useDismissedFindings.js';

// useDismissedFindings now reads useQueryClient() to fold restore/delete deltas
// into the RQ caches. Wrap renderHook in a provider so the hook has a client.
function withQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper };
}

vi.mock('../../../api/index.js', () => ({
  listDismissedFindings: vi.fn(),
  restoreFinding: vi.fn(),
  restoreAllFindings: vi.fn(),
  deleteFinding: vi.fn(),
  deleteAllFindings: vi.fn(),
  sharedListDismissedFindings: vi.fn(),
}));

vi.mock('../../../utils/confirmDialog.js', () => ({
  confirmDialog: vi.fn(),
}));

import {
  listDismissedFindings,
  restoreFinding,
  restoreAllFindings,
  deleteFinding,
  deleteAllFindings,
  sharedListDismissedFindings,
} from '../../../api/index.js';

import { confirmDialog } from '../../../utils/confirmDialog.js';

const sampleA = {
  req: 'A1', file: 'a.py', line: 10, severity: 'minor',
  dimension: 'security', principle: 'Path Validation',
};
const sampleB = {
  req: 'B1', file: 'b.py', line: 20, severity: 'major',
  dimension: 'reliability', principle: 'Fault Tolerance',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDismissedFindings — restore handlers', () => {
  it('handleRestore removes the matching entry on success and calls onRefresh', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    restoreFinding.mockResolvedValueOnce({ ok: true });
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleRestore(sampleA); });

    expect(restoreFinding).toHaveBeenCalledWith('proj', { req: 'A1', file: 'a.py', line: 10 });
    expect(result.current.dismissed).toEqual([sampleB]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(setRestoreError).not.toHaveBeenCalled();
  });

  it('handleRestore reports an error and leaves state unchanged on failure', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    restoreFinding.mockRejectedValueOnce(new Error('boom'));
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleRestore(sampleA); });

    expect(setRestoreError).toHaveBeenCalledWith('Failed to restore finding. Please try again.');
    expect(result.current.dismissed).toEqual([sampleA]);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('handleRestoreAll clears state on success and calls onRefresh', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    restoreAllFindings.mockResolvedValueOnce({ ok: true, restored: 2 });
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleRestoreAll(); });

    expect(restoreAllFindings).toHaveBeenCalledWith('proj');
    expect(result.current.dismissed).toEqual([]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});

describe('useDismissedFindings — handleDelete', () => {
  it('permanently deletes by (dimension, principle, file) and removes the entry locally', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    deleteFinding.mockResolvedValueOnce({ ok: true, swept: 1 });
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleDelete(sampleA); });

    expect(deleteFinding).toHaveBeenCalledWith('proj', {
      dimension: 'security',
      principle: 'Path Validation',
      file: 'a.py',
    });
    expect(restoreFinding).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([sampleB]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(setRestoreError).not.toHaveBeenCalled();
  });

  it('sweeps every dismissed entry sharing the same (dimension, principle, file)', async () => {
    const dupA = { ...sampleA, line: 99 };
    listDismissedFindings.mockResolvedValueOnce([sampleA, dupA, sampleB]);
    deleteFinding.mockResolvedValueOnce({ ok: true, swept: 2 });
    const { result } = renderHook(() => useDismissedFindings('proj', vi.fn(), vi.fn()), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(3));

    await act(async () => { await result.current.handleDelete(sampleA); });

    expect(result.current.dismissed).toEqual([sampleB]);
  });

  it('reports a delete-specific error and leaves state unchanged on failure', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    deleteFinding.mockRejectedValueOnce(new Error('boom'));
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleDelete(sampleA); });

    expect(setRestoreError).toHaveBeenCalledWith('Failed to delete finding. Please try again.');
    expect(result.current.dismissed).toEqual([sampleA]);
    expect(onRefresh).not.toHaveBeenCalled();
  });
});

describe('useDismissedFindings — handleDeleteAll', () => {
  it('opens the confirmation dialog and permanently deletes all on confirm', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(true);
    deleteAllFindings.mockResolvedValueOnce({ ok: true, deleted: 2 });
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleDeleteAll(); });

    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({
      variant: 'danger',
      title: 'Delete dismissed findings?',
      confirmLabel: 'Delete',
      message: expect.stringContaining('permanently delete those 2 findings'),
    }));
    expect(deleteAllFindings).toHaveBeenCalledWith('proj');
    expect(restoreAllFindings).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('does nothing when the user cancels the confirmation dialog', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(false);
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleDeleteAll(); });

    expect(confirmDialog).toHaveBeenCalledTimes(1);
    expect(deleteAllFindings).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([sampleA, sampleB]);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('reports a delete-specific error if deleteAllFindings fails after confirmation', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    confirmDialog.mockResolvedValueOnce(true);
    deleteAllFindings.mockRejectedValueOnce(new Error('boom'));
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleDeleteAll(); });

    expect(setRestoreError).toHaveBeenCalledWith('Failed to delete all findings. Please try again.');
    expect(result.current.dismissed).toEqual([sampleA]);
    expect(onRefresh).not.toHaveBeenCalled();
  });
});

// Shared projects have no mutation routes on the backend (dismiss/restore/
// delete are local-only by design, and the same project id can exist in both
// worlds). The dismissed list must read from the shared-repo mirror endpoint,
// and every mutation handler must no-op even if a callback somehow gets
// invoked — defense in depth on top of the caller passing `undefined` for
// these handlers when wiring the dismissed sub-tab.
describe('useDismissedFindings — shared source', () => {
  it('reads the dismissed list via the shared endpoint instead of the local one', async () => {
    sharedListDismissedFindings.mockResolvedValueOnce([sampleA]);
    const { result } = renderHook(
      () => useDismissedFindings('proj', vi.fn(), vi.fn(), 0, 'shared'),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    expect(sharedListDismissedFindings).toHaveBeenCalledWith('proj');
    expect(listDismissedFindings).not.toHaveBeenCalled();
  });

  it('handleRestore no-ops and never calls the local restore endpoint', async () => {
    sharedListDismissedFindings.mockResolvedValueOnce([sampleA]);
    const onRefresh = vi.fn();
    const { result } = renderHook(
      () => useDismissedFindings('proj', onRefresh, vi.fn(), 0, 'shared'),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleRestore(sampleA); });

    expect(restoreFinding).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([sampleA]);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('handleRestoreAll no-ops and never calls the local restore-all endpoint', async () => {
    sharedListDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    const { result } = renderHook(
      () => useDismissedFindings('proj', vi.fn(), vi.fn(), 0, 'shared'),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleRestoreAll(); });

    expect(restoreAllFindings).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([sampleA, sampleB]);
  });

  it('handleDelete no-ops and never calls the local delete endpoint', async () => {
    sharedListDismissedFindings.mockResolvedValueOnce([sampleA]);
    const { result } = renderHook(
      () => useDismissedFindings('proj', vi.fn(), vi.fn(), 0, 'shared'),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleDelete(sampleA); });

    expect(deleteFinding).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([sampleA]);
  });

  it('handleDeleteAll no-ops and never opens the confirm dialog', async () => {
    sharedListDismissedFindings.mockResolvedValueOnce([sampleA]);
    const { result } = renderHook(
      () => useDismissedFindings('proj', vi.fn(), vi.fn(), 0, 'shared'),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleDeleteAll(); });

    expect(confirmDialog).not.toHaveBeenCalled();
    expect(deleteAllFindings).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([sampleA]);
  });

  it('defaults to local source when selectedSource is omitted', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    const { result } = renderHook(
      () => useDismissedFindings('proj', vi.fn(), vi.fn()),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));
    expect(sharedListDismissedFindings).not.toHaveBeenCalled();
  });
});
