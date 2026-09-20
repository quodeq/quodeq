/**
 * Value-level characterization for useGalaxyCamera: the frame time step, the
 * idle star drift speeds/amplitudes, the principle orbit speeds and wobble,
 * the camera lerp factor and snap window, the per-depth zoom targets, the
 * cluster fit margin and the fit-zoom margin and cap.
 *
 * drawFrame is mocked so the loop never touches a real canvas; the mock
 * records the camera and the per-frame values it is handed.
 *
 * Captured from the pre-naming code — keep the snapshots unchanged.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const rec = vi.hoisted(() => ({ frames: [] }));

vi.mock('./galaxyViewDraw.js', () => ({
  drawFrame: (_ctx, _scene, cam, _nav, opts) => {
    rec.frames.push({ cam: { ...cam }, t: opts.t, rDim: opts.rDim, rPrin: opts.rPrin });
    return { hovered: null };
  },
}));

import { useGalaxyCamera } from './useGalaxyCamera.js';

const round = (n) => (typeof n === 'number' ? Number(n.toFixed(6)) : n);
const roundAll = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, round(v)]));
const camXYZ = (c) => ({ x: round(c.x), y: round(c.y), z: round(c.z) });

function makeScene(n, { clustered = false } = {}) {
  const stars = Array.from({ length: n }, (_, i) => ({
    x: 0, y: 0, ba: (i / n) * Math.PI, j: 5, radius: 10,
    ...(clustered ? { _clusterCx: 40, _clusterCy: -20, _ox: 12, _oy: 8 } : { _clusterCx: undefined }),
  }));
  const principles = stars.map(() => [
    { x: 0, y: 0, ba: 0, od: 30 },
    { x: 0, y: 0, ba: 1, od: 45 },
  ]);
  return {
    stars, principles, _maxExtent: 150,
    constellations: [{ cx: 40, cy: -20, spread: 60, lines: [] }],
  };
}

function makeRefs(navValue, canvasRef) {
  return {
    canvasRef: canvasRef || { current: null },
    savedCamRef: { current: null },
    navRef: { current: navValue },
    prevNavRef: { current: null },
    animRef: { current: null },
    mouseRef: { current: { x: -1, y: -1 } },
    hoveredRef: { current: null },
    focusedIdxRef: { current: null },
    frameRef: { current: null },
  };
}

function makeCanvasRef() {
  return { current: { getContext: () => ({}), parentElement: null } };
}

describe('useGalaxyCamera value characterization', () => {
  let rafCallbacks;
  let rafSpy;
  let cancelSpy;

  beforeEach(() => {
    rec.frames = [];
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

  it('drifts circular-layout stars at the recorded speeds, phases and amplitudes', () => {
    const scene = makeScene(3);
    const refs = makeRefs({ depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null }, makeCanvasRef());
    renderHook(() => useGalaxyCamera({ scene, size: { w: 800, h: 600 }, showLabels: false, ...refs }));
    tick(4);
    expect(rec.frames.map((f) => round(f.t))).toMatchSnapshot('frame-time-steps');
    expect(scene.stars.map((s) => roundAll({ x: s.x, y: s.y }))).toMatchSnapshot('circular-star-drift');
  });

  it('drifts clustered stars on their own sine/cosine speeds', () => {
    const scene = makeScene(3, { clustered: true });
    const refs = makeRefs({ depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null }, makeCanvasRef());
    renderHook(() => useGalaxyCamera({ scene, size: { w: 800, h: 600 }, showLabels: false, ...refs }));
    tick(4);
    expect(scene.stars.map((s) => roundAll({ x: s.x, y: s.y }))).toMatchSnapshot('clustered-star-drift');
  });

  it('orbits principles at the recorded per-index speed and wobble', () => {
    const scene = makeScene(2);
    const refs = makeRefs({ depth: 1, dim: 0, prin: null, clusterCx: null, clusterCy: null }, makeCanvasRef());
    renderHook(() => useGalaxyCamera({ scene, size: { w: 800, h: 600 }, showLabels: false, ...refs }));
    tick(5);
    expect(scene.principles[0].map((p) => roundAll({ x: p.x, y: p.y }))).toMatchSnapshot('principle-orbit');
  });

  it('snaps for the first frames then lerps toward the target by a fixed fraction', () => {
    const scene = makeScene(2);
    const refs = makeRefs({ depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null }, makeCanvasRef());
    renderHook(() => useGalaxyCamera({ scene, size: { w: 800, h: 600 }, showLabels: false, ...refs }));
    tick(3);
    // Move the target so the lerp has somewhere to go.
    refs.navRef.current = { depth: 1, dim: 0, prin: null, clusterCx: null, clusterCy: null };
    tick(6);
    expect(rec.frames.map((f) => camXYZ(f.cam))).toMatchSnapshot('camera-snap-then-lerp');
  });

  it('runs the transition easing when an animation is active', () => {
    const scene = makeScene(2);
    const refs = makeRefs({ depth: 1, dim: 0, prin: null, clusterCx: null, clusterCy: null }, makeCanvasRef());
    const { result } = renderHook(() => useGalaxyCamera({ scene, size: { w: 800, h: 600 }, showLabels: false, ...refs }));
    tick(4);
    act(() => { result.current.startTransition(false); });
    rec.frames = [];
    refs.navRef.current = { depth: 2, dim: 0, prin: 0, clusterCx: null, clusterCy: null };
    tick(30);
    expect(rec.frames.filter((_, i) => i % 5 === 0).map((f) => camXYZ(f.cam)))
      .toMatchSnapshot('camera-transition-track');
  });

  it('computes the per-depth zoom targets and the cluster fit margin', () => {
    const scene = makeScene(3);
    const size = { w: 800, h: 600 };
    const targets = {};
    for (const nav of [
      { key: 'galaxy', depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null },
      { key: 'cluster', depth: 0, dim: null, prin: null, clusterCx: 40, clusterCy: -20 },
      { key: 'unknown-cluster', depth: 0, dim: null, prin: null, clusterCx: 7, clusterCy: 7 },
      { key: 'dimension', depth: 1, dim: 1, prin: null, clusterCx: null, clusterCy: null },
      { key: 'principle', depth: 2, dim: 1, prin: 1, clusterCx: null, clusterCy: null },
    ]) {
      const refs = makeRefs(nav);
      const { result } = renderHook(() => useGalaxyCamera({ scene, size, showLabels: false, ...refs }));
      targets[nav.key] = roundAll(result.current.getTarget());
    }
    expect(targets).toMatchSnapshot('depth-targets');
  });

  it('fits the scene inside the view margin and caps the fit zoom', () => {
    const size = { w: 800, h: 600 };
    const fits = {};
    for (const ext of [null, 0, 150, 40, 5]) {
      const scene = { ...makeScene(2), _maxExtent: ext };
      const refs = makeRefs({ depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null });
      const { result } = renderHook(() => useGalaxyCamera({ scene, size, showLabels: false, ...refs }));
      fits['ext=' + ext] = round(result.current.getTarget().z);
    }
    expect(fits).toMatchSnapshot('fit-zoom-by-extent');
  });
});
