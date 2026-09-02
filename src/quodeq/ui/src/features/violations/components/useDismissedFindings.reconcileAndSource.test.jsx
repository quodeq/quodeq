import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useDismissedFindings } from './useDismissedFindings.js';

// Split from useDismissedFindings.test.jsx: the single onReconcile
// freshness-call contract, and shared-source read-only behavior. Shared
// mock header duplicated (vi.mock hoisting is file-scoped).

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

// The mutation handlers make exactly ONE freshness call: onReconcile (the
// debounced ACTIVE scheduleDashboardReconcile, which marks stale synchronously
// itself). onRefresh stays reserved for ViolationsPage's plain-navigation
// mount effect and must NOT be called by mutations -- wiring mutations to it
// as well was a redundant two-call ritual that call sites kept forgetting.
describe('useDismissedFindings — onReconcile (the single mutation freshness call)', () => {
  it('handleRestore calls onReconcile and leaves onRefresh untouched on success', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    restoreFinding.mockResolvedValueOnce({ ok: true });
    const onRefresh = vi.fn();
    const onReconcile = vi.fn();
    const { result } = renderHook(
      () => useDismissedFindings('proj', onRefresh, vi.fn(), 0, 'local', onReconcile),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleRestore(sampleA); });

    expect(onReconcile).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('handleRestore does not call onReconcile on failure', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    restoreFinding.mockRejectedValueOnce(new Error('boom'));
    const onReconcile = vi.fn();
    const { result } = renderHook(
      () => useDismissedFindings('proj', vi.fn(), vi.fn(), 0, 'local', onReconcile),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleRestore(sampleA); });

    expect(onReconcile).not.toHaveBeenCalled();
  });

  it('handleRestoreAll calls onReconcile and leaves onRefresh untouched on success', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(true);
    restoreAllFindings.mockResolvedValueOnce({ ok: true, restored: 2 });
    const onRefresh = vi.fn();
    const onReconcile = vi.fn();
    const { result } = renderHook(
      () => useDismissedFindings('proj', onRefresh, vi.fn(), 0, 'local', onReconcile),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleRestoreAll(); });

    expect(onReconcile).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('handleDelete calls onReconcile and leaves onRefresh untouched on success', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    deleteFinding.mockResolvedValueOnce({ ok: true, swept: 1 });
    const onRefresh = vi.fn();
    const onReconcile = vi.fn();
    const { result } = renderHook(
      () => useDismissedFindings('proj', onRefresh, vi.fn(), 0, 'local', onReconcile),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleDelete(sampleA); });

    expect(onReconcile).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('handleDeleteAll calls onReconcile and leaves onRefresh untouched on success', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(true);
    deleteAllFindings.mockResolvedValueOnce({ ok: true, deleted: 2 });
    const onRefresh = vi.fn();
    const onReconcile = vi.fn();
    const { result } = renderHook(
      () => useDismissedFindings('proj', onRefresh, vi.fn(), 0, 'local', onReconcile),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleDeleteAll(); });

    expect(onReconcile).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('handleDeleteAll does not call onReconcile when the user cancels', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(false);
    const onReconcile = vi.fn();
    const { result } = renderHook(
      () => useDismissedFindings('proj', vi.fn(), vi.fn(), 0, 'local', onReconcile),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleDeleteAll(); });

    expect(onReconcile).not.toHaveBeenCalled();
  });

  it('works fine when onReconcile is omitted (optional param, back-compat)', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    restoreFinding.mockResolvedValueOnce({ ok: true });
    const { result } = renderHook(
      () => useDismissedFindings('proj', vi.fn(), vi.fn()),
      withQueryClient(),
    );
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleRestore(sampleA); });

    expect(result.current.dismissed).toEqual([sampleB]);
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
