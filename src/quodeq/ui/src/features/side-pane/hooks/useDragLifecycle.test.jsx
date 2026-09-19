import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDragLifecycle } from './useDragLifecycle.js';

function setup() {
  const setResizingFlag = vi.fn();
  const activeDragCleanupRef = { current: null };
  const { result } = renderHook(() => useDragLifecycle({ setResizingFlag, activeDragCleanupRef }));
  return { beginDrag: result.current, setResizingFlag, activeDragCleanupRef };
}

function gesture(overrides = {}) {
  return {
    cursor: 'row-resize',
    onMove: vi.fn(),
    onFrame: vi.fn(),
    onEnd: vi.fn(),
    ...overrides,
  };
}

describe('useDragLifecycle', () => {
  let frames;

  // React schedules frames of its own, so the suite asserts on what the hook
  // does when frames run rather than on how many are outstanding.
  const flushFrames = () => {
    const pending = frames.splice(0);
    pending.forEach((cb) => { if (cb) cb(); });
  };

  beforeEach(() => {
    frames = [];
    vi.stubGlobal('requestAnimationFrame', (cb) => frames.push(cb));
    vi.stubGlobal('cancelAnimationFrame', (id) => { frames[id - 1] = null; });
    document.body.style.cursor = 'auto';
    document.body.style.userSelect = 'text';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('claims the body cursor and selection and raises the resizing flag', () => {
    const { beginDrag, setResizingFlag } = setup();
    act(() => { beginDrag(gesture({ cursor: 'col-resize' })); });
    expect(document.body.style.cursor).toBe('col-resize');
    expect(document.body.style.userSelect).toBe('none');
    expect(setResizingFlag).toHaveBeenCalledWith(true);
  });

  it('calls onMove on every pointermove but onFrame at most once per frame', () => {
    const { beginDrag } = setup();
    const g = gesture();
    act(() => { beginDrag(g); });

    act(() => {
      window.dispatchEvent(new Event('pointermove'));
      window.dispatchEvent(new Event('pointermove'));
      window.dispatchEvent(new Event('pointermove'));
    });
    expect(g.onMove).toHaveBeenCalledTimes(3);
    expect(g.onFrame).not.toHaveBeenCalled();

    act(() => { flushFrames(); });
    expect(g.onFrame).toHaveBeenCalledTimes(1);

    // The frame has run, so the next move schedules a fresh one.
    act(() => { window.dispatchEvent(new Event('pointermove')); });
    act(() => { flushFrames(); });
    expect(g.onFrame).toHaveBeenCalledTimes(2);
  });

  it('hands the pointer event to onMove', () => {
    const { beginDrag } = setup();
    const g = gesture();
    act(() => { beginDrag(g); });
    const event = new Event('pointermove');
    act(() => { window.dispatchEvent(event); });
    expect(g.onMove).toHaveBeenCalledWith(event);
  });

  it('runs onEnd with the pointerup event, then restores everything', () => {
    const { beginDrag, setResizingFlag, activeDragCleanupRef } = setup();
    const order = [];
    const g = gesture({ onEnd: vi.fn(() => order.push('end')) });
    act(() => { beginDrag(g); });
    expect(activeDragCleanupRef.current).toBeTypeOf('function');

    const up = new Event('pointerup');
    act(() => { window.dispatchEvent(up); });

    expect(g.onEnd).toHaveBeenCalledWith(up);
    expect(order).toEqual(['end']);
    expect(document.body.style.cursor).toBe('auto');
    expect(document.body.style.userSelect).toBe('text');
    expect(setResizingFlag).toHaveBeenLastCalledWith(false);
    expect(activeDragCleanupRef.current).toBeNull();
  });

  it('stops listening after the gesture ends', () => {
    const { beginDrag } = setup();
    const g = gesture();
    act(() => { beginDrag(g); });
    act(() => { window.dispatchEvent(new Event('pointerup')); });
    act(() => { window.dispatchEvent(new Event('pointermove')); });
    expect(g.onMove).not.toHaveBeenCalled();
  });

  it('cancels a pending frame when the drag is torn down mid-gesture', () => {
    const { beginDrag } = setup();
    const g = gesture();
    let cleanup;
    act(() => { cleanup = beginDrag(g); });
    act(() => { window.dispatchEvent(new Event('pointermove')); });
    act(() => { cleanup(); });
    act(() => { flushFrames(); });
    expect(g.onFrame).not.toHaveBeenCalled();
  });

  it('publishes a cleanup an unmount can run mid-drag', () => {
    const { beginDrag, activeDragCleanupRef, setResizingFlag } = setup();
    act(() => { beginDrag(gesture()); });
    act(() => { activeDragCleanupRef.current(); });
    expect(document.body.style.cursor).toBe('auto');
    expect(setResizingFlag).toHaveBeenLastCalledWith(false);
    expect(activeDragCleanupRef.current).toBeNull();
  });
});
