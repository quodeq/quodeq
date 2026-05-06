import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useDismissedFindings } from './useDismissedFindings.js';

vi.mock('../../../api/index.js', () => ({
  listDismissedFindings: vi.fn(),
  restoreFinding: vi.fn(),
  restoreAllFindings: vi.fn(),
  deleteFinding: vi.fn(),
  deleteAllFindings: vi.fn(),
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
  it('handleRestore removes the matching entry on success and calls onRefresh', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    restoreFinding.mockResolvedValueOnce({ ok: true });
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError));
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
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError));
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
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError));
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
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError));
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
    const { result } = renderHook(() => useDismissedFindings('proj', vi.fn(), vi.fn()));
    await waitFor(() => expect(result.current.dismissed).toHaveLength(3));

    await act(async () => { await result.current.handleDelete(sampleA); });

    expect(result.current.dismissed).toEqual([sampleB]);
  });

  it('reports a delete-specific error and leaves state unchanged on failure', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    deleteFinding.mockRejectedValueOnce(new Error('boom'));
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError));
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
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError));
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
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError));
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
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError));
    await waitFor(() => expect(result.current.dismissed).toHaveLength(1));

    await act(async () => { await result.current.handleDeleteAll(); });

    expect(setRestoreError).toHaveBeenCalledWith('Failed to delete all findings. Please try again.');
    expect(result.current.dismissed).toEqual([sampleA]);
    expect(onRefresh).not.toHaveBeenCalled();
  });
});
