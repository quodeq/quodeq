import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useOneShotGate } from './useOneShotGate.js';

// The startup loader must be a boot-scoped one-shot: once it has dropped,
// it may never re-arm. Without the gate, a mid-session project switch to a
// not-yet-loaded overview (opening a project from Compare) re-satisfies
// the hold predicate and flashes the fullscreen loader over the app.
describe('useOneShotGate', () => {
  it('passes the active value through while it has never dropped', () => {
    const { result, rerender } = renderHook(({ active }) => useOneShotGate(active), {
      initialProps: { active: true },
    });
    expect(result.current).toBe(true);
    rerender({ active: true });
    expect(result.current).toBe(true);
  });

  it('latches off permanently after the first inactive render', () => {
    const { result, rerender } = renderHook(({ active }) => useOneShotGate(active), {
      initialProps: { active: true },
    });
    rerender({ active: false });
    expect(result.current).toBe(false);
    rerender({ active: true });
    expect(result.current).toBe(false);
  });

  it('starting inactive consumes the gate immediately', () => {
    const { result, rerender } = renderHook(({ active }) => useOneShotGate(active), {
      initialProps: { active: false },
    });
    expect(result.current).toBe(false);
    rerender({ active: true });
    expect(result.current).toBe(false);
  });
});
