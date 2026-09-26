import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useViolationsTabKeyReset } from './useViolationsPageState.js';
import { createPageStateCache, readCachedState, writeCachedState, clearAllCachedState } from '../../../utils/pageStateCache.js';

describe('useViolationsTabKeyReset: page-state cache injection', () => {
  beforeEach(() => clearAllCachedState());
  afterEach(() => clearAllCachedState());

  it('reads from an injected cache and leaves the default (module) cache untouched', () => {
    const injected = createPageStateCache();
    injected.writeCachedState('violations', 'proj-x', { fileCurrentPath: 'src/foo' });

    const { result } = renderHook(() =>
      useViolationsTabKeyReset({ tabKey: 0, selectedProject: 'proj-x', onRefresh: () => {}, cache: injected })
    );

    expect(result.current.fileCurrentPath).toBe('src/foo');
    // The default cache never saw this scope: nothing was written there.
    expect(readCachedState('violations', 'proj-x', { fileCurrentPath: '' }).fileCurrentPath).toBe('');
  });

  it('with no cache prop, it still reads from the default (module) cache -- unchanged production behavior', () => {
    writeCachedState('violations', 'proj-y', { fileCurrentPath: 'src/bar' });

    const { result } = renderHook(() =>
      useViolationsTabKeyReset({ tabKey: 0, selectedProject: 'proj-y', onRefresh: () => {} })
    );

    expect(result.current.fileCurrentPath).toBe('src/bar');
    expect(readCachedState('violations', 'proj-y', {}).fileCurrentPath).toBe('src/bar');
  });
});
