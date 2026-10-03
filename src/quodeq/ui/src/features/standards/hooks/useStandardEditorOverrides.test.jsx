import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

vi.mock('./useStandardsOverrides.js', () => ({ useStandardsOverrides: vi.fn() }));
vi.mock('../../../hooks/useAppState.js', () => ({ useAppState: vi.fn() }));

import { useStandardsOverrides } from './useStandardsOverrides.js';
import { useAppState } from '../../../hooks/useAppState.js';
import { useStandardEditorOverrides } from './useStandardEditorOverrides.js';

const STANDARD = { id: 'accessibility', name: 'Accessibility', managed: false, principles: [] };

function setup(save) {
  useAppState.mockReturnValue({ selectedProject: 'proj' });
  useStandardsOverrides.mockReturnValue({ overrides: {}, save: vi.fn(), preview: vi.fn() });
  const onSaved = vi.fn();
  const { result } = renderHook(() => useStandardEditorOverrides({ standard: STANDARD, editable: true, save, onSaved }));
  return { result, onSaved };
}

// A rejected save used to still call onSaved, which sent the user back to the
// list as if the change had landed, hiding the inline error.
describe('useStandardEditorOverrides commitSave', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('does not report the save as done when the standard save fails', async () => {
    const save = vi.fn(async () => ({ error: 'Standard not found: accessibility-v2' }));
    const { result, onSaved } = setup(save);

    await act(async () => { await result.current.commitSave(); });

    expect(save).toHaveBeenCalledOnce();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('reports the saved id when the standard save succeeds', async () => {
    const save = vi.fn(async () => ({ error: null }));
    const { result, onSaved } = setup(save);

    await act(async () => { await result.current.commitSave(); });

    expect(onSaved).toHaveBeenCalledWith('accessibility');
  });
});
