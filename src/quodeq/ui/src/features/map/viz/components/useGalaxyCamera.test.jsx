import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Mock drawFrame before the hook module is imported so the animation loop
// does not hit real canvas / DOM APIs (parseCSSColor, getThemeColors).
vi.mock('./galaxyViewDraw.js', () => ({
  drawFrame: vi.fn(() => ({ hovered: null })),
}));

import { useGalaxyCamera } from './useGalaxyCamera.js';

// Minimal scene factory — build a scene with `n` stars each having one principle.
function makeScene(n) {
  const stars = Array.from({ length: n }, (_, i) => ({
    x: 100 + i * 10,
    y: 200 + i * 10,
    ba: 0,
    j: 5,
    _clusterCx: undefined,
  }));
  const principles = stars.map((s) => [
    { x: s.x + 5, y: s.y + 5, ba: 0, od: 10 },
  ]);
  return { stars, principles, _maxExtent: 150, constellations: [] };
}

function makeRefs(navValue) {
  return {
    canvasRef: { current: null },       // no real canvas needed for getTarget tests
    savedNavRef: { current: null },
    savedCamRef: { current: null },
    navRef: { current: navValue },
    prevNavRef: { current: null },
    animRef: { current: null },
    mouseRef: { current: { x: 0, y: 0 } },
    hoveredRef: { current: null },
    frameRef: { current: null },
  };
}

describe('useGalaxyCamera — getTarget stale-index guard (#387)', () => {
  it('returns safe center/zoom default at depth 1 when nav.dim is out of range for the current scene', () => {
    // Simulate: nav was set when scene had 5 stars (dim=4); a new scene with only 2 stars is received.
    const scene = makeScene(2);
    const size = { w: 800, h: 600 };
    const refs = makeRefs({ depth: 1, dim: 4, prin: null, clusterCx: null, clusterCy: null });

    const { result } = renderHook(() =>
      useGalaxyCamera({ scene, size, showLabels: false, ...refs })
    );

    let target;
    act(() => {
      target = result.current.getTarget();
    });

    // Must not throw; must fall back to center
    expect(target).toEqual({ x: size.w / 2, y: size.h / 2, z: expect.any(Number) });
  });

  it('returns safe center/zoom default at depth 2 when nav.dim is out of range', () => {
    const scene = makeScene(2);
    const size = { w: 800, h: 600 };
    const refs = makeRefs({ depth: 2, dim: 4, prin: 0, clusterCx: null, clusterCy: null });

    const { result } = renderHook(() =>
      useGalaxyCamera({ scene, size, showLabels: false, ...refs })
    );

    let target;
    act(() => {
      target = result.current.getTarget();
    });

    expect(target).toEqual({ x: size.w / 2, y: size.h / 2, z: expect.any(Number) });
  });

  it('returns safe center/zoom default at depth 2 when nav.prin is out of range', () => {
    const scene = makeScene(3);
    const size = { w: 800, h: 600 };
    // dim=1 is valid (scene has 3 stars) but prin=5 is out of range (only 1 principle per star)
    const refs = makeRefs({ depth: 2, dim: 1, prin: 5, clusterCx: null, clusterCy: null });

    const { result } = renderHook(() =>
      useGalaxyCamera({ scene, size, showLabels: false, ...refs })
    );

    let target;
    act(() => {
      target = result.current.getTarget();
    });

    expect(target).toEqual({ x: size.w / 2, y: size.h / 2, z: expect.any(Number) });
  });

  it('returns the correct star target at depth 1 for a valid in-range index', () => {
    const scene = makeScene(3);
    const size = { w: 800, h: 600 };
    const refs = makeRefs({ depth: 1, dim: 1, prin: null, clusterCx: null, clusterCy: null });

    const { result } = renderHook(() =>
      useGalaxyCamera({ scene, size, showLabels: false, ...refs })
    );

    let target;
    act(() => {
      target = result.current.getTarget();
    });

    // The hook renders without a canvas so stars won't have been position-updated,
    // but their initial x/y are set in makeScene.
    expect(target).toMatchObject({ z: 5 });
  });

  it('returns the correct principle target at depth 2 for valid in-range indices', () => {
    const scene = makeScene(3);
    const size = { w: 800, h: 600 };
    const refs = makeRefs({ depth: 2, dim: 0, prin: 0, clusterCx: null, clusterCy: null });

    const { result } = renderHook(() =>
      useGalaxyCamera({ scene, size, showLabels: false, ...refs })
    );

    let target;
    act(() => {
      target = result.current.getTarget();
    });

    expect(target).toMatchObject({ z: 50 });
  });
});

// ---------------------------------------------------------------------------
// updatePrinciplePositions stale-star guard in the animation loop (#387 follow-up)
// ---------------------------------------------------------------------------
// The animation loop calls updatePrinciplePositions(scene.principles[rDim], scene.stars[rDim], t).
// rDim comes from nav.dim ?? prev?.dim ?? null and can be a stale index after a scene rebuild
// (scene.stars[rDim] === undefined). We can't drive requestAnimationFrame directly in jsdom,
// so we test the guard at the unit level: the internal helper must not throw when the star
// lookup yields undefined. We verify this by calling the hook with a canvas stub that lets
// one rAF tick fire and asserting no error is thrown even when prevNavRef.dim is out of range.
describe('useGalaxyCamera — animation-loop stale-star guard', () => {
  let rafCallbacks;
  let rafSpy;
  let cancelSpy;

  beforeEach(() => {
    rafCallbacks = [];
    rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb) => {
      const id = rafCallbacks.push(cb);
      return id;
    });
    cancelSpy = vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {});
  });

  afterEach(() => {
    rafSpy.mockRestore();
    cancelSpy.mockRestore();
  });

  function makeCanvasRef() {
    const ctx = {
      clearRect: vi.fn(),
      save: vi.fn(), restore: vi.fn(),
      beginPath: vi.fn(), arc: vi.fn(), fill: vi.fn(), stroke: vi.fn(),
      fillText: vi.fn(), measureText: vi.fn(() => ({ width: 10 })),
      createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
      createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
      drawImage: vi.fn(),
      canvas: { width: 800, height: 600 },
    };
    const canvas = {
      getContext: vi.fn(() => ctx),
      width: 800,
      height: 600,
      parentElement: null,
    };
    return { current: canvas };
  }

  it('does not throw when rDim from prevNavRef is out of range for the current scene', () => {
    // scene has 2 stars; prevNavRef.dim = 4 (stale from previous larger scene)
    const scene = makeScene(2);
    const size = { w: 800, h: 600 };

    const refs = {
      ...makeRefs({ depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null }),
      canvasRef: makeCanvasRef(),
      // prevNavRef carries the stale dim that drives rDim in the animation loop
      prevNavRef: { current: { dim: 4, prin: null } },
    };

    // Rendering the hook registers the animation loop via useEffect.
    expect(() => {
      renderHook(() =>
        useGalaxyCamera({ scene, size, showLabels: false, ...refs })
      );
      // Fire one animation frame tick — this is where the crash would occur.
      if (rafCallbacks.length > 0) {
        rafCallbacks[0]();
      }
    }).not.toThrow();
  });

  it('does not throw when nav.dim itself is out of range for the current scene', () => {
    // scene has 2 stars; nav.dim = 5 (stale)
    const scene = makeScene(2);
    const size = { w: 800, h: 600 };

    const refs = {
      ...makeRefs({ depth: 1, dim: 5, prin: null, clusterCx: null, clusterCy: null }),
      canvasRef: makeCanvasRef(),
    };

    expect(() => {
      renderHook(() =>
        useGalaxyCamera({ scene, size, showLabels: false, ...refs })
      );
      if (rafCallbacks.length > 0) {
        rafCallbacks[0]();
      }
    }).not.toThrow();
  });
});
