import { describe, it, expect, vi } from 'vitest';
import { handleCanvasClick, focusableNodes, createKeyboardHandlers } from './galaxyViewEvents.js';

describe('handleCanvasClick', () => {
  it('does not throw when camRef.current is null during a cluster-click hit-test', () => {
    // Simulate the null window: camera not yet initialised
    const refs = {
      hoveredRef: { current: null },
      navRef: { current: { depth: 0, clusterCx: null, clusterCy: null } },
      animRef: { current: false },
      camRef: { current: null },        // <-- the null value under test
      canvasRef: {
        current: {
          getBoundingClientRect: () => ({ left: 0, top: 0 }),
        },
      },
    };

    const scene = {
      constellations: [{ cx: 0, cy: 0, spread: 10 }],
    };

    const e = { clientX: 50, clientY: 50 };
    const size = { w: 800, h: 600 };
    const navigateTo = vi.fn();
    const startTransition = vi.fn();
    const saveNav = vi.fn();
    const w2s = (x, y) => ({ x, y });

    expect(() =>
      handleCanvasClick(e, refs, scene, size, navigateTo, startTransition, saveNav, w2s)
    ).not.toThrow();
  });
});

function makeScene() {
  return {
    stars: [
      { name: 'Reliability', score: 8.2 },
      { name: 'Performance', score: 7.1 },
      { name: 'Security', score: 6.5 },
    ],
    principles: {
      0: [{ name: 'Error Handling', score: 9 }, { name: 'Retries', score: 5 }],
    },
  };
}

function makeRefs(nav) {
  return {
    navRef: { current: nav },
    animRef: { current: null },
    focusedIdxRef: { current: null },
  };
}

function makeParams(scene, overrides = {}) {
  return {
    scene,
    navigateTo: vi.fn(),
    startTransition: vi.fn(),
    saveNav: vi.fn(),
    announce: vi.fn(),
    ...overrides,
  };
}

const key = (k) => ({ key: k, preventDefault: vi.fn() });

describe('focusableNodes (#675)', () => {
  it('returns dimension stars at depth 0', () => {
    expect(focusableNodes(makeScene(), { depth: 0 })).toHaveLength(3);
  });

  it('returns the active dimension principles at depth 1', () => {
    expect(focusableNodes(makeScene(), { depth: 1, dim: 0 })).toHaveLength(2);
  });

  it('returns an empty list at depth 2 (no siblings to traverse)', () => {
    expect(focusableNodes(makeScene(), { depth: 2, dim: 0, prin: 0 })).toEqual([]);
  });

  it('returns an empty list for a null scene', () => {
    expect(focusableNodes(null, { depth: 0 })).toEqual([]);
  });
});

describe('createKeyboardHandlers (#675)', () => {
  it('ArrowRight from no focus selects the first node and announces it', () => {
    const refs = makeRefs({ depth: 0 });
    const params = makeParams(makeScene());
    createKeyboardHandlers(refs, params).handleKeyDown(key('ArrowRight'));
    expect(refs.focusedIdxRef.current).toBe(0);
    expect(params.announce).toHaveBeenCalledWith('Reliability, score 8.2, 1 of 3');
  });

  it('ArrowLeft from no focus selects the last node', () => {
    const refs = makeRefs({ depth: 0 });
    createKeyboardHandlers(refs, makeParams(makeScene())).handleKeyDown(key('ArrowLeft'));
    expect(refs.focusedIdxRef.current).toBe(2);
  });

  it('ArrowRight wraps from the last node back to the first', () => {
    const refs = makeRefs({ depth: 0 });
    refs.focusedIdxRef.current = 2;
    createKeyboardHandlers(refs, makeParams(makeScene())).handleKeyDown(key('ArrowRight'));
    expect(refs.focusedIdxRef.current).toBe(0);
  });

  it('Enter at depth 0 drills into the focused dimension', () => {
    const refs = makeRefs({ depth: 0 });
    refs.focusedIdxRef.current = 1;
    const params = makeParams(makeScene());
    createKeyboardHandlers(refs, params).handleKeyDown(key('Enter'));
    expect(params.navigateTo).toHaveBeenCalledWith(1, 1);
    expect(refs.focusedIdxRef.current).toBeNull();
  });

  it('Enter at depth 1 drills into the focused principle', () => {
    const refs = makeRefs({ depth: 1, dim: 0 });
    refs.focusedIdxRef.current = 1;
    const params = makeParams(makeScene());
    createKeyboardHandlers(refs, params).handleKeyDown(key('Enter'));
    expect(params.navigateTo).toHaveBeenCalledWith(2, 0, 1);
  });

  it('Enter with nothing focused does nothing', () => {
    const refs = makeRefs({ depth: 0 });
    const params = makeParams(makeScene());
    createKeyboardHandlers(refs, params).handleKeyDown(key('Enter'));
    expect(params.navigateTo).not.toHaveBeenCalled();
  });

  it('Escape at depth 2 returns to the principle list', () => {
    const refs = makeRefs({ depth: 2, dim: 0, prin: 1 });
    const params = makeParams(makeScene());
    createKeyboardHandlers(refs, params).handleKeyDown(key('Escape'));
    expect(params.navigateTo).toHaveBeenCalledWith(1, 0);
  });

  it('Escape at depth 1 returns to the galaxy overview', () => {
    const refs = makeRefs({ depth: 1, dim: 0 });
    const params = makeParams(makeScene());
    createKeyboardHandlers(refs, params).handleKeyDown(key('Escape'));
    expect(params.navigateTo).toHaveBeenCalledWith(0);
  });

  it('Escape inside a cluster at depth 0 resets the cluster', () => {
    const nav = { depth: 0, clusterCx: 10, clusterCy: 20 };
    const refs = makeRefs(nav);
    const params = makeParams(makeScene());
    createKeyboardHandlers(refs, params).handleKeyDown(key('Escape'));
    expect(nav.clusterCx).toBeNull();
    expect(params.startTransition).toHaveBeenCalledWith(true);
  });

  it('ignores key input while a camera transition is animating', () => {
    const refs = makeRefs({ depth: 0 });
    refs.animRef.current = { t: 0.3 };
    const params = makeParams(makeScene());
    createKeyboardHandlers(refs, params).handleKeyDown(key('ArrowRight'));
    expect(refs.focusedIdxRef.current).toBeNull();
    expect(params.announce).not.toHaveBeenCalled();
  });

  it('handleFocus auto-focuses the first node', () => {
    const refs = makeRefs({ depth: 0 });
    createKeyboardHandlers(refs, makeParams(makeScene())).handleFocus();
    expect(refs.focusedIdxRef.current).toBe(0);
  });

  it('handleBlur clears focus', () => {
    const refs = makeRefs({ depth: 0 });
    refs.focusedIdxRef.current = 1;
    createKeyboardHandlers(refs, makeParams(makeScene())).handleBlur();
    expect(refs.focusedIdxRef.current).toBeNull();
  });
});
