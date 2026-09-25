import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import useMapPageState from './useMapPageState.js';
import { writeVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { createPageStateCache, readCachedState, clearAllCachedState } from '../../../utils/pageStateCache.js';

vi.mock('../../../api/standards.js', () => ({
  listStandards: vi.fn().mockResolvedValue([]),
}));

const dims = (...names) => names.map((dimension) => ({ dimension, id: dimension }));

function setup(props) {
  return renderHook(
    (p) => useMapPageState(p),
    {
      initialProps: {
        data: { projectName: 'proj-x', accumulated: { dimensions: dims('Security', 'Performance') } },
        callbacks: {},
        nav: null,
        tabKey: 0,
        ...props,
      },
    }
  );
}

describe('useMapPageState: page-state cache injection', () => {
  beforeEach(() => {
    localStorage.clear();
    writeVisibleStandardIds(['security', 'performance']);
    clearAllCachedState();
  });

  afterEach(() => {
    localStorage.clear();
    clearAllCachedState();
  });

  it('writes a toggle into an injected cache and leaves the default (module) cache untouched', () => {
    const injected = createPageStateCache();
    const { result } = setup({ cache: injected });

    act(() => { result.current.dimensionState.onToggleDimension('Security'); });

    expect(injected.readCachedState('map', 'proj-x', {}).selectedDimensionsArr).toEqual(['Performance']);
    // The shared, module-lived default cache never saw this write.
    expect(readCachedState('map', 'proj-x', {})).toEqual({});
  });

  it('with no cache prop, the toggle still writes into the default (module) cache -- unchanged production behavior', () => {
    const { result } = setup();

    act(() => { result.current.dimensionState.onToggleDimension('Security'); });

    expect(readCachedState('map', 'proj-x', {}).selectedDimensionsArr).toEqual(['Performance']);
  });
});
