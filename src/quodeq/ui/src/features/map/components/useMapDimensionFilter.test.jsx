import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMapDimensionFilter } from './useMapDimensionFilter.js';
import { writeVisibleStandardIds } from '../../../utils/visibleStandards.js';
import { readCachedState } from '../../../utils/pageStateCache.js';

const dims = (...names) => names.map((dimension) => ({ dimension, id: dimension }));

function setup(props) {
  return renderHook(
    ({ allDimensions, selectedProject, cachedSelectedArr }) =>
      useMapDimensionFilter({ allDimensions, selectedProject, cachedSelectedArr }),
    {
      initialProps: {
        allDimensions: dims('Security', 'Maintainability', 'Performance'),
        selectedProject: 'p1',
        cachedSelectedArr: [],
        ...props,
      },
    }
  );
}

describe('useMapDimensionFilter', () => {
  beforeEach(() => {
    localStorage.clear();
    writeVisibleStandardIds(['security', 'maintainability', 'performance']);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('keeps only the dimensions whose lower-cased name is a visible standard', () => {
    writeVisibleStandardIds(['security', 'performance']);
    const { result } = setup();
    expect(result.current.dimensionNames).toEqual(['Performance', 'Security']);
    expect(result.current.filteredDimensions.map((d) => d.dimension)).toEqual(['Security', 'Performance']);
  });

  it('an empty selection means no filter: every visible dimension shows', () => {
    const { result } = setup();
    expect(result.current.effectiveSelected).toEqual(new Set(['Maintainability', 'Performance', 'Security']));
    expect(result.current.filteredDimensions).toHaveLength(3);
  });

  it('toggling a dimension off narrows the selection', () => {
    const { result } = setup();
    act(() => { result.current.handleToggleDimension('Security'); });
    expect(result.current.effectiveSelected).toEqual(new Set(['Maintainability', 'Performance']));
    expect(result.current.filteredDimensions.map((d) => d.dimension))
      .toEqual(['Maintainability', 'Performance']);
  });

  it('toggling the last dimension off falls back to showing everything', () => {
    const { result } = setup({ cachedSelectedArr: ['Security'] });
    act(() => { result.current.handleToggleDimension('Security'); });
    expect(result.current.effectiveSelected).toEqual(new Set(['Maintainability', 'Performance', 'Security']));
  });

  it('toggling every dimension back on collapses to the no-filter empty set', () => {
    const { result } = setup({ cachedSelectedArr: ['Security', 'Performance'] });
    act(() => { result.current.handleToggleDimension('Maintainability'); });
    expect(result.current.effectiveSelected).toEqual(new Set(['Maintainability', 'Performance', 'Security']));
    expect(result.current.filteredDimensions).toHaveLength(3);
  });

  it('writes the surviving selection to the page-state cache on every toggle', () => {
    const { result } = setup();
    act(() => { result.current.handleToggleDimension('Security'); });
    expect(readCachedState('map', 'p1').selectedDimensionsArr.sort())
      .toEqual(['Maintainability', 'Performance']);
  });

  // The visibility memo must key on the visible ids, not on allDimensions:
  // hiding a standard elsewhere has to reach the map even though the same
  // dimensions array comes back in.
  it('re-reads the visible standards when they change, without allDimensions moving', () => {
    const allDimensions = dims('Security', 'Maintainability', 'Performance');
    const props = { allDimensions, selectedProject: 'p1', cachedSelectedArr: [] };
    const { result, rerender } = renderHook((p) => useMapDimensionFilter(p), { initialProps: props });
    expect(result.current.dimensionNames).toHaveLength(3);
    act(() => { writeVisibleStandardIds(['security']); });
    rerender({ ...props });
    expect(result.current.dimensionNames).toEqual(['Security']);
  });
});
