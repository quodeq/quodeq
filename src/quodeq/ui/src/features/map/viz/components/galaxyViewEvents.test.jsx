import { describe, it, expect, vi } from 'vitest';
import { handleCanvasClick } from './galaxyViewEvents.js';

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
