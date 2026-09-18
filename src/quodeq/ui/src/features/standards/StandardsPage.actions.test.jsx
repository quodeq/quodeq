import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useStandardsPageActions } from './StandardsPage.jsx';

// handleDeleteWithCleanup used to remove a standard's visibility optimistically
// and await the delete with no way to react to a failure -- a failed delete
// left the standard hidden even though it still existed. It must now restore
// the optimistic removal and log instead.
describe('useStandardsPageActions handleDeleteWithCleanup', () => {
  it('restores visibility and logs when the delete fails', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const refresh = vi.fn();
    const handleDelete = vi.fn(async () => false); // makeHandleDelete's failure return
    const addVisible = vi.fn();
    const removeVisible = vi.fn();

    const { result } = renderHook(() => useStandardsPageActions(refresh, handleDelete, addVisible, removeVisible));

    await act(async () => {
      await result.current.handleDeleteWithCleanup('std-1');
    });

    expect(removeVisible).toHaveBeenCalledWith('std-1');
    expect(handleDelete).toHaveBeenCalledWith('std-1');
    expect(addVisible).toHaveBeenCalledWith('std-1');
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('[StandardsPage]'),
      'std-1',
    );
    warn.mockRestore();
  });

  it('does not restore visibility when the delete succeeds', async () => {
    const refresh = vi.fn();
    const handleDelete = vi.fn(async () => true);
    const addVisible = vi.fn();
    const removeVisible = vi.fn();

    const { result } = renderHook(() => useStandardsPageActions(refresh, handleDelete, addVisible, removeVisible));

    await act(async () => {
      await result.current.handleDeleteWithCleanup('std-1');
    });

    expect(removeVisible).toHaveBeenCalledWith('std-1');
    expect(addVisible).not.toHaveBeenCalled();
  });
});
