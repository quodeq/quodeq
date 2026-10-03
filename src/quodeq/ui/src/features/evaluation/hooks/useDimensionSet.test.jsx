import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDimensionSet } from './useDimensionSet.js';

const DIMS = [{ id: 'security' }, { id: 'usability' }];

describe('useDimensionSet', () => {
  it('toggles, selects all and clears', () => {
    const { result } = renderHook(() => useDimensionSet(DIMS));
    expect([...result.current.selectedDims]).toEqual([]);
    act(() => result.current.toggleDim('security'));
    expect([...result.current.selectedDims]).toEqual(['security']);
    act(() => result.current.toggleDim('security'));
    expect([...result.current.selectedDims]).toEqual([]);
    act(() => result.current.selectAll());
    expect([...result.current.selectedDims]).toEqual(['security', 'usability']);
    act(() => result.current.clearAll());
    expect(result.current.selectedDims.size).toBe(0);
  });

  it('refuses an empty selection when dimensions are available', () => {
    const onValidationFail = vi.fn();
    const { result } = renderHook(() => useDimensionSet(DIMS));
    expect(result.current.refuseEmptySelection(onValidationFail)).toBe(true);
    expect(onValidationFail).toHaveBeenCalledTimes(1);
    expect(typeof onValidationFail.mock.calls[0][0]).toBe('string');
    expect(result.current.refuseEmptySelection(undefined)).toBe(true);
  });

  it('allows the start once something is selected, or when there is nothing to pick', () => {
    const onValidationFail = vi.fn();
    const picked = renderHook(() => useDimensionSet(DIMS));
    act(() => picked.result.current.toggleDim('usability'));
    expect(picked.result.current.refuseEmptySelection(onValidationFail)).toBe(false);
    const none = renderHook(() => useDimensionSet([]));
    expect(none.result.current.refuseEmptySelection(onValidationFail)).toBe(false);
    expect(onValidationFail).not.toHaveBeenCalled();
  });
});
