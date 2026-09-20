/**
 * Value-level characterization for galaxyFolderCamera: the fly-in/fly-out
 * swap points, the zoom multipliers on either side of a swap, the scene and
 * bloom alpha ramps, the frame time step, the idle lerp factor, the snap
 * window and the easing curves advanceCamera runs.
 *
 * Captured from the pre-naming code — keep the snapshots unchanged.
 */
import { describe, it, expect, vi } from 'vitest';

vi.mock('./galaxyFolderScene.js', () => ({
  buildFolderScene: vi.fn(() => ({ rootStars: [], lines: [], bg: [], _maxExtent: 100 })),
}));

import { advanceFlyTransition, advanceCamera } from './galaxyFolderCamera.js';

const round = (n) => (typeof n === 'number' ? Number(n.toFixed(6)) : n);
const snapCam = (cam, a) => ({
  x: round(cam.x), y: round(cam.y), z: round(cam.z),
  sceneAlpha: round(a.sceneAlpha), bloomAlpha: round(a.bloomAlpha),
});

function makeRefs() {
  return {
    zoomedFileRef: { current: null },
    focusedFolderRef: { current: null },
    navRef: { current: { path: [{ name: 'root' }] } },
    sceneRef: { current: { rootStars: [], _node: { name: 'root' } } },
    nextSceneRef: { current: { rootStars: [], _maxExtent: 120 } },
    frameCount: { current: 0 },
    animRef: { current: null },
    prevNavRef: { current: null },
    flyRef: { current: null },
  };
}

/** Run the fly transition to completion, sampling the camera every `every` steps. */
function runFly(fly, cam, refs, params, every) {
  const samples = [];
  let i = 0;
  while (fly.t < 1) {
    const alphas = advanceFlyTransition(fly, cam, refs, params);
    if (i % every === 0 || fly.t >= 1) samples.push([round(fly.t), snapCam(cam, alphas)]);
    i++;
    if (i > 500) break;
  }
  return samples;
}

describe('galaxyFolderCamera fly transitions', () => {
  it('fly-in zooms, swaps the scene at its swap point, then blooms out', () => {
    const refs = makeRefs();
    const cam = { x: 100, y: 100, z: 2 };
    const fly = {
      t: 0, reverse: false, swapped: false, dimStarIdx: 0,
      sx: 100, sy: 100, sz: 2, starX: 300, starY: 250,
      newPath: [{ name: 'root' }, { name: 'src' }], targetNode: { name: 'src' },
    };
    const saveNav = vi.fn();
    const samples = runFly(fly, cam, refs, {
      W: 800, H: 600, FLY_DURATION: 1.4, getFitZoom: () => 1.5, saveNav,
    }, 8);
    expect(samples).toMatchSnapshot('fly-in-camera-track');
    expect(fly.swapped).toBe(true);
    expect(saveNav).toHaveBeenCalledTimes(1);
    expect(refs.frameCount.current).toBe(0);
  });

  it('fly-out shrinks, swaps to the parent scene, then grows the bloom in', () => {
    const refs = makeRefs();
    const cam = { x: 100, y: 100, z: 6 };
    const fly = {
      t: 0, reverse: true, swapped: false,
      sx: 100, sy: 100, sz: 6, newPath: [{ name: 'root' }],
    };
    const samples = runFly(fly, cam, refs, {
      W: 800, H: 600, FLY_DURATION: 1.4, getFitZoom: () => 1.5, saveNav: vi.fn(),
    }, 8);
    expect(samples).toMatchSnapshot('fly-out-camera-track');
    expect(refs.zoomedFileRef.current).toBeNull();
    expect(refs.focusedFolderRef.current).toBeNull();
  });

  it('the frame time step advances fly.t by the same amount every call', () => {
    const refs = makeRefs();
    const cam = { x: 0, y: 0, z: 1 };
    const fly = { t: 0, reverse: true, swapped: false, sx: 0, sy: 0, sz: 1, newPath: [] };
    const params = { W: 800, H: 600, FLY_DURATION: 1.4, getFitZoom: () => 1, saveNav: vi.fn() };
    advanceFlyTransition(fly, cam, refs, params);
    const first = fly.t;
    advanceFlyTransition(fly, cam, refs, params);
    expect(round(fly.t - first)).toBe(round(first));
    expect(round(first)).toMatchSnapshot('fly-time-step');
  });
});

describe('galaxyFolderCamera advanceCamera', () => {
  const target = { x: 400, y: 300, z: 3 };

  function run(refs, cam, steps) {
    const track = [];
    for (let i = 0; i < steps; i++) {
      advanceCamera(cam, refs, {
        TRANS: 0.8, scene: { rootStars: [] }, computeFocusCamera: () => target, W: 800, H: 600,
      });
      track.push({ x: round(cam.x), y: round(cam.y), z: round(cam.z) });
    }
    return track;
  }

  it('snaps straight to the target for the first frames, then lerps', () => {
    const refs = makeRefs();
    const cam = { x: 0, y: 0, z: 1 };
    const track = run(refs, cam, 8);
    // The snap window: the camera is already on target on frame one.
    expect(track[0]).toEqual({ x: 400, y: 300, z: 3 });
    expect(track).toMatchSnapshot('idle-snap-then-lerp');
  });

  it('lerps toward the target by a fixed fraction once past the snap window', () => {
    const refs = makeRefs();
    refs.frameCount.current = 50;
    const cam = { x: 0, y: 0, z: 1 };
    expect(run(refs, cam, 6)).toMatchSnapshot('idle-lerp-track');
  });

  it('runs the transition easing curves to completion and clears the anim', () => {
    const refs = makeRefs();
    refs.frameCount.current = 50;
    refs.animRef.current = { t: 0, sx: 0, sy: 0, sz: 1, out: false };
    const cam = { x: 0, y: 0, z: 1 };
    const track = run(refs, cam, 55);
    expect(track.filter((_, i) => i % 5 === 0)).toMatchSnapshot('transition-in-track');
    expect(refs.animRef.current).toBeNull();
    expect(refs.prevNavRef.current).toBeNull();
  });

  it('swaps which easing drives position and zoom when zooming out', () => {
    const refs = makeRefs();
    refs.frameCount.current = 50;
    refs.animRef.current = { t: 0, sx: 0, sy: 0, sz: 1, out: true };
    const cam = { x: 0, y: 0, z: 1 };
    const track = run(refs, cam, 55);
    expect(track.filter((_, i) => i % 5 === 0)).toMatchSnapshot('transition-out-track');
  });

  it('auto-enters a focused folder once its zoom transition finishes', () => {
    const refs = makeRefs();
    refs.frameCount.current = 50;
    refs.animRef.current = { t: 0.99, sx: 0, sy: 0, sz: 1, out: false };
    refs.focusedFolderRef.current = {
      starIdx: 0, autoEnter: true,
      x: 10, y: 20,
    };
    refs.sceneRef.current = {
      rootStars: [{ isFolder: true, x: 10, y: 20, col: { r: 1, g: 2, b: 3 }, radius: 5, _node: { name: 'src' } }],
    };
    const cam = { x: 0, y: 0, z: 1 };
    run(refs, cam, 2);
    expect(refs.flyRef.current).toMatchObject({ t: 0, starX: 10, starY: 20, dimStarIdx: 0, swapped: false });
    expect(refs.focusedFolderRef.current).toBeNull();
  });
});
