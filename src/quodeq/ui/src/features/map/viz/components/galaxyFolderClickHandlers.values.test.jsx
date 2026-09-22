/**
 * Value-level characterization for galaxyFolderClickHandlers' zoom-toward-
 * cursor branch: the bias between the raw cursor and the nearest star, the
 * per-click zoom step and the cap the step is clamped to.
 *
 * Captured from the pre-naming code — keep the snapshots unchanged.
 */
import { describe, it, expect, vi } from 'vitest';

vi.mock('../core/galaxyCore.js', () => ({ getThemeColors: () => ({ gradeMid: { r: 1, g: 2, b: 3 } }) }));
vi.mock('./galaxyFolderScene.js', () => ({
  buildFolderScene: vi.fn(() => ({ rootStars: [], lines: [], bg: [], _maxExtent: 50 })),
}));

import { handleEmptySpaceClick } from './galaxyFolderClickHandlers.js';

const round = (n) => (typeof n === 'number' ? Number(n.toFixed(6)) : n);

function makeRefs(mouse) {
  return {
    camRef: { current: { x: 400, y: 300, z: 2 } },
    mouseRef: { current: mouse },
    sceneRef: { current: { rootStars: [{ x: 500, y: 200 }, { x: 100, y: 500 }] } },
    zoomedFileRef: { current: null },
    zoomTargetRef: { current: null },
    focusedFolderRef: { current: null },
    flyRef: { current: null },
    nextSceneRef: { current: null },
  };
}

const size = { w: 800, h: 600 };

function clickEmpty(refs, getFitZoom) {
  handleEmptySpaceClick(refs, { path: [{ name: 'root' }] }, {
    startTransition: vi.fn(), saveNav: vi.fn(),
    getFitZoom: getFitZoom || (() => 1), scene: refs.sceneRef.current, size,
  });
}

describe('galaxyFolderClickHandlers zoom-toward-cursor values', () => {
  it('biases the target between the cursor and the nearest star and steps the zoom', () => {
    const refs = makeRefs({ x: 600, y: 200 });
    clickEmpty(refs);
    expect({
      x: round(refs.zoomTargetRef.current.x),
      y: round(refs.zoomTargetRef.current.y),
      z: round(refs.zoomTargetRef.current.z),
    }).toMatchSnapshot('zoom-toward-cursor-target');
  });

  it('clamps the stepped zoom to the fit-zoom cap', () => {
    const refs = makeRefs({ x: 600, y: 200 });
    refs.camRef.current.z = 100;
    clickEmpty(refs, () => 1);
    expect(round(refs.zoomTargetRef.current.z)).toMatchSnapshot('zoom-toward-cursor-cap');
  });

  it('falls back to the raw cursor position when the scene has no stars', () => {
    const refs = makeRefs({ x: 600, y: 200 });
    refs.sceneRef.current = { rootStars: [] };
    clickEmpty(refs);
    expect({
      x: round(refs.zoomTargetRef.current.x),
      y: round(refs.zoomTargetRef.current.y),
    }).toMatchSnapshot('zoom-toward-cursor-no-stars');
  });

  it('does nothing while the cursor is off-canvas', () => {
    const refs = makeRefs({ x: -1, y: -1 });
    clickEmpty(refs);
    expect(refs.zoomTargetRef.current).toBeNull();
  });
});
