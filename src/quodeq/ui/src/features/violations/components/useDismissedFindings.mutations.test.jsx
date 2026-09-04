import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDismissedFindings } from './useDismissedFindings.js';

// Split from useDismissedFindings.test.jsx: restore/delete/deleteAll
// mutation handlers. Shared mock header duplicated (vi.mock hoisting is
// file-scoped).

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
  it('handleRestore removes the matching entry on success and calls onReconcile', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    restoreFinding.mockResolvedValueOnce({ ok: true });
    const onReconcile = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', vi.fn(), setRestoreError, 0, 'local', onReconcile), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleRestore(sampleA); });

    expect(restoreFinding).toHaveBeenCalledWith('proj', { req: 'A1', file: 'a.py', line: 10 });
    expect(result.current.dismissed).toEqual([sampleB]);
    expect(onReconcile).toHaveBeenCalledTimes(1);
    expect(setRestoreError).not.toHaveBeenCalled();
  });

  it('handleRestore reports an error and leaves state unchanged on failure', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    restoreFinding.mockRejectedValueOnce(new Error('boom'));
    const onRefresh = vi.fn();
    const onReconcile = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError, 0, 'local', onReconcile), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleRestore(sampleA); });

    expect(setRestoreError).toHaveBeenCalledWith('Failed to restore finding. Please try again.');
    expect(result.current.dismissed).toEqual([sampleA]);
    expect(onRefresh).not.toHaveBeenCalled();
    expect(onReconcile).not.toHaveBeenCalled();
  });

  it('handleRestoreAll clears state on success and calls onReconcile', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(true);
    restoreAllFindings.mockResolvedValueOnce({ ok: true, restored: 2 });
    const onReconcile = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', vi.fn(), setRestoreError, 0, 'local', onReconcile), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleRestoreAll(); });

    expect(restoreAllFindings).toHaveBeenCalledWith('proj');
    expect(result.current.dismissed).toEqual([]);
    expect(onReconcile).toHaveBeenCalledTimes(1);
  });

  // Restore-all un-suppresses every finding the user has ever triaged away, and
  // the only undo is re-dismissing them one by one. It sits next to the
  // per-item Restore button, so an unguarded click silently wiped 2045
  // dismissals in the real project. Delete-all has always confirmed; this must
  // too.
  it('handleRestoreAll asks for confirmation before restoring', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(true);
    restoreAllFindings.mockResolvedValueOnce({ ok: true, restored: 2 });
    const { result } = renderHook(() => useDismissedFindings('proj', vi.fn(), vi.fn(), 0, 'local', vi.fn()), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleRestoreAll(); });

    expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Restore dismissed findings?',
      confirmLabel: 'Restore all',
      message: expect.stringContaining('2'),
    }));
    expect(restoreAllFindings).toHaveBeenCalledWith('proj');
  });

  it('handleRestoreAll does nothing when the user cancels', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(false);
    const onReconcile = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', vi.fn(), vi.fn(), 0, 'local', onReconcile), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleRestoreAll(); });

    expect(confirmDialog).toHaveBeenCalledTimes(1);
    expect(restoreAllFindings).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([sampleA, sampleB]);
    expect(onReconcile).not.toHaveBeenCalled();
  });
});

describe('useDismissedFindings — handleDelete', () => {
  it('permanently deletes by (dimension, principle, file) and removes the entry locally', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    deleteFinding.mockResolvedValueOnce({ ok: true, swept: 1 });
    const onReconcile = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', vi.fn(), setRestoreError, 0, 'local', onReconcile), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleDelete(sampleA); });

    expect(deleteFinding).toHaveBeenCalledWith('proj', {
      dimension: 'security',
      principle: 'Path Validation',
      file: 'a.py',
    });
    expect(restoreFinding).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([sampleB]);
    expect(onReconcile).toHaveBeenCalledTimes(1);
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
    const onReconcile = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError, 0, 'local', onReconcile), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleDelete(sampleA); });

    expect(setRestoreError).toHaveBeenCalledWith('Failed to delete finding. Please try again.');
    expect(result.current.dismissed).toEqual([sampleA]);
    expect(onReconcile).not.toHaveBeenCalled();
  });
});

describe('useDismissedFindings — handleDeleteAll', () => {
  it('opens the confirmation dialog and permanently deletes all on confirm', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(true);
    deleteAllFindings.mockResolvedValueOnce({ ok: true, deleted: 2 });
    const onReconcile = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', vi.fn(), setRestoreError, 0, 'local', onReconcile), withQueryClient());
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
    expect(onReconcile).toHaveBeenCalledTimes(1);
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

  // Task E5: routed through apiErrorMessage now (see useDismissedFindings.js),
  // matching the same map-through-apiErrorMessage pattern already applied to
  // the delete-project/publish/session-start call sites. An unmapped code (or
  // no code at all, as here) still surfaces the backend's own specific
  // message rather than the vague fixed fallback the old code always showed
  // -- apiErrorMessage's documented precedence (see strings/apiErrors.js).
  it('reports the backend message if deleteAllFindings fails after confirmation with no mapped code', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    confirmDialog.mockResolvedValueOnce(true);
    deleteAllFindings.mockRejectedValueOnce(new Error('boom'));
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleDeleteAll(); });

    expect(setRestoreError).toHaveBeenCalledWith('boom');
    expect(result.current.dismissed).toEqual([sampleA]);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  // The delete-all route's own confirm gate (CONFIRMATION_REQUIRED, see
  // routes_findings.py) -- unreachable through this hook in practice since
  // api/findings.js's deleteAllFindings always sends ?confirm=true, but the
  // mapping must still work correctly for any error that does carry the code
  // (a future direct caller, a race, or a backend change).
  it('maps a CONFIRMATION_REQUIRED failure to its translated copy', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    confirmDialog.mockResolvedValueOnce(true);
    const err = new Error('Use ?confirm=true to confirm deletion');
    err.code = 'CONFIRMATION_REQUIRED';
    deleteAllFindings.mockRejectedValueOnce(err);
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', vi.fn(), setRestoreError), withQueryClient());
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleDeleteAll(); });

    expect(setRestoreError).toHaveBeenCalledWith('Confirm the deletion and try again.');
  });
});
