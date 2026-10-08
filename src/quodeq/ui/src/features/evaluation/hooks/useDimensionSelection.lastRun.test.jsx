import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDimensionSelection } from './useDimensionSelection.js';

// The setup card starts from the last run's dimensions when nothing else
// asked for a selection, and never overrides what the user picked.
const dims = [{ id: 'security' }, { id: 'reliability' }, { id: 'accessibility' }];
const args = (o) => ({ allDimensions: dims, info: { path: '/r' }, onStart: vi.fn(), onValidationFail: vi.fn(), preselectDims: [], ...o });

describe('useDimensionSelection, last run', () => {
  it('starts from the last run when navigation preselects nothing', () => {
    const { result } = renderHook(() => useDimensionSelection(args({ fallbackDims: ['security', 'reliability'] })));
    expect([...result.current.selectedDims].sort()).toEqual(['reliability', 'security']);
    expect(result.current.seededFromLastRun).toBe(true);
  });

  it('navigation preselection wins over the last run', () => {
    const { result } = renderHook(() => useDimensionSelection(args({ preselectDims: ['accessibility'], fallbackDims: ['security'] })));
    expect([...result.current.selectedDims]).toEqual(['accessibility']);
    expect(result.current.seededFromLastRun).toBe(false);
  });

  it('a late seed never clobbers a toggle', () => {
    const { result, rerender } = renderHook((p) => useDimensionSelection(args(p)), { initialProps: { fallbackDims: [] } });
    act(() => result.current.toggleDim('accessibility'));
    rerender({ fallbackDims: ['security'] });
    expect([...result.current.selectedDims]).toEqual(['accessibility']);
    expect(result.current.seededFromLastRun).toBe(false);
  });

  it('last-run dimensions that are not on the card are ignored', () => {
    const { result } = renderHook(() => useDimensionSelection(args({ fallbackDims: ['domain-driven-design', 'security'] })));
    expect([...result.current.selectedDims]).toEqual(['security']);
  });
});
