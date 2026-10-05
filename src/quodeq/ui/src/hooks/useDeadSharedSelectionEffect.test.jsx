import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useDeadSharedSelectionEffect } from './useAppEffects.js';
import { PROJECT_SOURCE } from '../vocab/projectSource.js';

// A restored shared selection is exempt from the "no projects" rules, so it
// needs a repository behind it. Victor's wiped ~/.quodeq (2026-10-05) kept a
// shared selection in the webview's storage (which lives outside the folder)
// and the app sat on a dead shared Overview: no landing, no welcome. The
// server's own "nothing connected" answer drops that selection; a failed
// status fetch does not.

function props({ selectedSource = PROJECT_SOURCE.SHARED, connected = false, handleProjectChange }) {
  return {
    state: { selectedSource, handleProjectChange },
    sharedSignal: { settled: connected !== null, hasContent: false, publishedCount: 0, connected },
  };
}

function renderEffect(initial) {
  const handleProjectChange = vi.fn();
  const utils = renderHook((p) => useDeadSharedSelectionEffect(p), { initialProps: props({ ...initial, handleProjectChange }) });
  const update = (next) => utils.rerender(props({ ...initial, ...next, handleProjectChange }));
  return { ...utils, handleProjectChange, update };
}

describe('useDeadSharedSelectionEffect', () => {
  it('drops a shared selection once the server says no repository is connected', () => {
    const { handleProjectChange } = renderEffect({});
    expect(handleProjectChange).toHaveBeenCalledWith('');
  });

  it('waits for the status answer, then drops', () => {
    const { handleProjectChange, update } = renderEffect({ connected: null });
    expect(handleProjectChange).not.toHaveBeenCalled();
    update({ connected: false });
    expect(handleProjectChange).toHaveBeenCalledWith('');
  });

  it('keeps a shared selection while a repository is connected', () => {
    const { handleProjectChange } = renderEffect({ connected: true });
    expect(handleProjectChange).not.toHaveBeenCalled();
  });

  it('keeps a shared selection when the status fetch failed (connected unknown)', () => {
    const { handleProjectChange } = renderEffect({ connected: null });
    expect(handleProjectChange).not.toHaveBeenCalled();
  });

  it('leaves a local selection alone', () => {
    const { handleProjectChange } = renderEffect({ selectedSource: PROJECT_SOURCE.LOCAL });
    expect(handleProjectChange).not.toHaveBeenCalled();
  });

  it('drops only once: the cleared selection is local and re-renders are quiet', () => {
    const { handleProjectChange, update } = renderEffect({});
    update({ selectedSource: PROJECT_SOURCE.LOCAL });
    update({ selectedSource: PROJECT_SOURCE.LOCAL });
    expect(handleProjectChange).toHaveBeenCalledTimes(1);
  });
});
