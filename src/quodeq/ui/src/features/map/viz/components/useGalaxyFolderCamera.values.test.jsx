/**
 * Value-level characterization for useGalaxyFolderCamera: the frame time
 * step, the initial-fly and invisibility alpha cutoffs, the fit-zoom view
 * margin and cap, and every branch of the focus-camera zoom math (zoomed
 * file, explicit zoom target, focused-folder preview, fit-everything).
 *
 * The draw module is mocked so the loop never touches a real canvas; the
 * mock records the per-frame bundle it is handed. The first frames take
 * advanceCamera's snap branch, so camRef lands exactly on the focus target.
 *
 * Captured from the pre-naming code — keep the snapshots unchanged.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const rec = vi.hoisted(() => ({ frames: [], alphas: [] }));

vi.mock('./galaxyFolderDraw.js', () => ({
  drawScene: () => ({ tc: { text: {}, textMuted: {} } }),
  drawNebula: (_ctx, _n, frame) => rec.frames.push({ t: frame.t, cam: { ...frame.cam } }),
  drawStarfield: () => {},
  drawConstellationLines: () => {},
  drawStars: () => ({ pendingLabels: [], newHovered: null }),
  drawLabels: () => {},
}));

import { useGalaxyFolderCamera } from './useGalaxyFolderCamera.js';

const round = (n) => (typeof n === 'number' ? Number(n.toFixed(6)) : n);
const camXYZ = (c) => ({ x: round(c.x), y: round(c.y), z: round(c.z) });

function makeCtx() {
  const target = {};
  return new Proxy(target, {
    get: (t, p) => (p in t ? t[p] : (t[p] = () => {})),
    set: (t, p, v) => { if (p === 'globalAlpha') rec.alphas.push(round(v)); t[p] = v; return true; },
  });
}

function makeScene(stars) {
  return { rootStars: stars || [], lines: [], bg: [], _maxExtent: 100, _node: { name: 'root' } };
}

function makeRefs(scene) {
  return {
    canvasRef: { current: { getContext: () => makeCtx(), parentElement: null } },
    camRef: { current: null },
    flyRef: { current: null },
    sceneRef: { current: scene },
    nextSceneRef: { current: null },
    navRef: { current: { path: [{ name: 'root' }] } },
    mouseRef: { current: { x: -1, y: -1 } },
    hoveredRef: { current: null },
    frameRef: { current: null },
    focusedFolderRef: { current: null },
    zoomedFileRef: { current: null },
    zoomTargetRef: { current: null },
    animRef: { current: null },
    prevNavRef: { current: null },
    frameCount: { current: 0 },
  };
}

describe('useGalaxyFolderCamera value characterization', () => {
  let rafCallbacks;
  let rafSpy;
  let cancelSpy;

  beforeEach(() => {
    rec.frames = []; rec.alphas = [];
    rafCallbacks = [];
    rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb) => rafCallbacks.push(cb));
    cancelSpy = vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {});
  });
  afterEach(() => { rafSpy.mockRestore(); cancelSpy.mockRestore(); });

  function tick(times) {
    for (let i = 0; i < times; i++) {
      const cb = rafCallbacks.shift();
      if (!cb) break;
      act(() => { cb(); });
    }
  }

  function render(refs, scene) {
    return renderHook(() => useGalaxyFolderCamera({
      refs, scene, showLabels: false, saveNav: vi.fn(), setNavVersion: vi.fn(),
    }));
  }

  it('advances the clock by a fixed frame step', () => {
    const scene = makeScene();
    const refs = makeRefs(scene);
    render(refs, scene);
    tick(4);
    expect(rec.frames.map((f) => round(f.t))).toMatchSnapshot('frame-time-steps');
  });

  it('fits the scene inside the view margin and caps the fit zoom', () => {
    const scene = makeScene();
    const refs = makeRefs(scene);
    const { result } = render(refs, scene);
    const fits = {};
    for (const ext of [null, 0, 100, 60, 10]) {
      fits['ext=' + ext] = round(result.current.getFitZoom({ _maxExtent: ext }));
    }
    expect(fits).toMatchSnapshot('fit-zoom-by-extent');
  });

  it('targets the fit-everything centre when nothing is focused', () => {
    const scene = makeScene();
    const refs = makeRefs(scene);
    render(refs, scene);
    tick(1);
    expect(camXYZ(refs.camRef.current)).toMatchSnapshot('focus-target-default');
  });

  it('floors a zoomed file at the recorded minimum zoom', () => {
    const scene = makeScene();
    const refs = makeRefs(scene);
    refs.zoomedFileRef.current = { x: 120, y: 90, starIdx: 0 };
    render(refs, scene);
    tick(1);
    expect(camXYZ(refs.camRef.current)).toMatchSnapshot('focus-target-zoomed-file');
  });

  it('uses an explicit zoom target verbatim', () => {
    const scene = makeScene();
    const refs = makeRefs(scene);
    refs.zoomTargetRef.current = { x: 5, y: 6, z: 7.5 };
    render(refs, scene);
    tick(1);
    expect(camXYZ(refs.camRef.current)).toMatchSnapshot('focus-target-explicit');
  });

  it('sizes a focused-folder preview from the star radius and screen fraction', () => {
    const star = { x: 200, y: 150, radius: 12, isFolder: true, ox: 0, oy: 0, col: {}, particles: [], _node: {} };
    const scene = makeScene([star]);
    const refs = makeRefs(scene);
    refs.focusedFolderRef.current = { x: 200, y: 150, starIdx: 0, autoEnter: false };
    render(refs, scene);
    tick(1);
    expect(camXYZ(refs.camRef.current)).toMatchSnapshot('focus-target-folder-preview');
  });

  it('falls back to a default preview radius when the star is missing', () => {
    const scene = makeScene([]);
    const refs = makeRefs(scene);
    refs.focusedFolderRef.current = { x: 200, y: 150, starIdx: 3, autoEnter: false };
    render(refs, scene);
    tick(1);
    expect(camXYZ(refs.camRef.current)).toMatchSnapshot('focus-target-missing-star');
  });

  it('paints the initial fly frame at the recorded alpha', () => {
    const scene = makeScene();
    const refs = makeRefs(scene);
    refs.nextSceneRef.current = makeScene();
    refs.flyRef.current = {
      t: 0, reverse: false, swapped: false, dimStarIdx: 0,
      sx: 0, sy: 0, sz: 1, starX: 10, starY: 10, newPath: [{ name: 'root' }],
    };
    render(refs, scene);
    tick(1);
    expect(rec.alphas).toMatchSnapshot('initial-fly-alpha');
  });

  it('ramps the scene and bloom alphas across a whole fly-in', () => {
    const scene = makeScene();
    const refs = makeRefs(scene);
    refs.nextSceneRef.current = makeScene();
    refs.flyRef.current = {
      t: 0, reverse: false, swapped: false, dimStarIdx: 0,
      sx: 0, sy: 0, sz: 1, starX: 10, starY: 10, newPath: [{ name: 'root' }],
      targetNode: { name: 'src' },
    };
    render(refs, scene);
    tick(60);
    // Every frame writes the effective alpha then restores it to 1; keep the
    // effective one and sample it so the snapshot stays readable.
    const effective = rec.alphas.filter((_, i) => i % 2 === 0);
    expect(effective.filter((_, i) => i % 4 === 0)).toMatchSnapshot('fly-in-alpha-ramp');
  });
});
