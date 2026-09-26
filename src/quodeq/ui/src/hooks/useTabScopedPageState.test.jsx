import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { createPageStateCache } from '../utils/pageStateCache.js';
import { useTabScopedPageState } from './useTabScopedPageState.js';

function renderScoped(cache, tabKey) {
  return renderHook((props) => useTabScopedPageState({
    namespace: 'page', scope: 'proj', defaults: { path: '' }, cache, ...props,
  }), { initialProps: { tabKey } });
}

describe('useTabScopedPageState', () => {
  it('keeps the cached state across remounts with the same tabKey', () => {
    const cache = createPageStateCache();
    cache.writeCachedState('page', 'proj', { path: 'src/a' });
    const { result } = renderScoped(cache, 1);
    expect(result.current).toEqual({ path: 'src/a' });
  });

  it('drops the scope when tabKey changes and reads the defaults', () => {
    const cache = createPageStateCache();
    cache.writeCachedState('page', 'proj', { path: 'src/a' });
    const { result, rerender } = renderScoped(cache, 1);
    rerender({ tabKey: 2 });
    expect(result.current).toEqual({ path: '' });
  });
});
