import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { useDismissedFindings } from './useDismissedFindings.js';

vi.mock('../../../api/index.js', () => ({
  listDismissedFindings: vi.fn(),
  restoreFinding: vi.fn(),
  restoreAllFindings: vi.fn(),
}));

vi.mock('../../../utils/confirmDialog.js', () => ({
  confirmDialog: vi.fn(),
}));

import {
  listDismissedFindings,
  restoreFinding,
  restoreAllFindings,
} from '../../../api/index.js';

import { confirmDialog } from '../../../utils/confirmDialog.js';

const sampleA = { req: 'A1', file: 'a.py', line: 10, severity: 'minor' };
const sampleB = { req: 'B1', file: 'b.py', line: 20, severity: 'major' };

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
  it('removes the matching entry on success and calls onRefresh (mirrors restore on disk, distinct error message)', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    restoreFinding.mockResolvedValueOnce({ ok: true });
    const onRefresh = vi.fn();
    const setRestoreError = vi.fn();
    const { result } = renderHook(() => useDismissedFindings('proj', onRefresh, setRestoreError));
    await waitFor(() => expect(result.current.dismissed).toHaveLength(2));

    await act(async () => { await result.current.handleDelete(sampleA); });

    expect(restoreFinding).toHaveBeenCalledWith('proj', { req: 'A1', file: 'a.py', line: 10 });
    expect(result.current.dismissed).toEqual([sampleB]);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    expect(setRestoreError).not.toHaveBeenCalled();
  });

  it('reports a delete-specific error and leaves state unchanged on failure', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    restoreFinding.mockRejectedValueOnce(new Error('boom'));
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
  it('opens the confirmation dialog and clears state when the user confirms', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA, sampleB]);
    confirmDialog.mockResolvedValueOnce(true);
    restoreAllFindings.mockResolvedValueOnce({ ok: true, restored: 2 });
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
    expect(restoreAllFindings).toHaveBeenCalledWith('proj');
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
    expect(restoreAllFindings).not.toHaveBeenCalled();
    expect(result.current.dismissed).toEqual([sampleA, sampleB]);
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('reports a delete-specific error if restoreAllFindings fails after confirmation', async () => {
    listDismissedFindings.mockResolvedValueOnce([sampleA]);
    confirmDialog.mockResolvedValueOnce(true);
    restoreAllFindings.mockRejectedValueOnce(new Error('boom'));
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
