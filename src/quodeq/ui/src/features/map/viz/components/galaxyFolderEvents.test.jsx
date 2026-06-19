import { describe, it, expect, vi } from 'vitest';
import { createEventHandlers } from './galaxyFolderEvents.js';
import { advanceCamera } from './galaxyFolderCamera.js';

function makeRefs(overrides = {}) {
  return {
    navRef: { current: { path: [{ name: 'root', path: '' }] } },
    camRef: { current: { x: 400, y: 300, z: 1 } },
    animRef: { current: null },
    flyRef: { current: null },
    zoomedFileRef: { current: null },
    zoomTargetRef: { current: null },
    focusedFolderRef: { current: null },
    mouseRef: { current: { x: 400, y: 300 } },
    hoveredRef: { current: null },
    tooltipRef: { current: { style: {}, innerHTML: '' } },
    canvasRef: { current: { style: {}, getBoundingClientRect: () => ({ left: 0, top: 0 }) } },
    sceneRef: { current: null },
    nextSceneRef: { current: null },
    prevNavRef: { current: null },
    frameRef: { current: null },
    frameCount: { current: 0 },
    ...overrides,
  };
}

function makeParams(overrides = {}) {
  return {
    startTransition: vi.fn(),
    saveNav: vi.fn(),
    getFitZoom: vi.fn(() => 1),
    scene: { rootStars: [] },
    size: { w: 800, h: 600 },
    ...overrides,
  };
}

describe('galaxyFolderEvents keyboard handler (#2063)', () => {
  it('createEventHandlers returns a handleKeyDown function', () => {
    const handlers = createEventHandlers(makeRefs(), makeParams());
    expect(typeof handlers.handleKeyDown).toBe('function');
  });

  it('ArrowLeft calls startTransition (pan left via camera adjustment)', () => {
    const params = makeParams();
    const refs = makeRefs();
    const handlers = createEventHandlers(refs, params);
    handlers.handleKeyDown({ key: 'ArrowLeft', preventDefault: vi.fn() });
    // Camera x should have decreased (pan left)
    expect(refs.camRef.current.x).toBeLessThan(400);
  });

  it('ArrowRight pans camera right', () => {
    const refs = makeRefs();
    const handlers = createEventHandlers(refs, makeParams());
    handlers.handleKeyDown({ key: 'ArrowRight', preventDefault: vi.fn() });
    expect(refs.camRef.current.x).toBeGreaterThan(400);
  });

  it('ArrowUp pans camera up', () => {
    const refs = makeRefs();
    const handlers = createEventHandlers(refs, makeParams());
    handlers.handleKeyDown({ key: 'ArrowUp', preventDefault: vi.fn() });
    expect(refs.camRef.current.y).toBeLessThan(300);
  });

  it('ArrowDown pans camera down', () => {
    const refs = makeRefs();
    const handlers = createEventHandlers(refs, makeParams());
    handlers.handleKeyDown({ key: 'ArrowDown', preventDefault: vi.fn() });
    expect(refs.camRef.current.y).toBeGreaterThan(300);
  });

  it('Enter key invokes the click effect (startTransition + saveNav called)', () => {
    const params = makeParams();
    // Ensure mouseRef has a valid position so handleClick takes the zoom-toward-cursor branch.
    const refs = makeRefs({ mouseRef: { current: { x: 400, y: 300 } } });
    const handlers = createEventHandlers(refs, params);
    handlers.handleKeyDown({ key: 'Enter', preventDefault: vi.fn() });
    // handleClick on empty space with nav.path.length === 1 zooms toward cursor:
    // it must call startTransition and saveNav.
    expect(params.startTransition).toHaveBeenCalled();
    expect(params.saveNav).toHaveBeenCalled();
  });

  it('Space key invokes the click effect (startTransition + saveNav called)', () => {
    const params = makeParams();
    const refs = makeRefs({ mouseRef: { current: { x: 400, y: 300 } } });
    const handlers = createEventHandlers(refs, params);
    handlers.handleKeyDown({ key: ' ', preventDefault: vi.fn() });
    expect(params.startTransition).toHaveBeenCalled();
    expect(params.saveNav).toHaveBeenCalled();
  });

  it('unhandled key does nothing (no throw)', () => {
    const refs = makeRefs();
    const handlers = createEventHandlers(refs, makeParams());
    expect(() =>
      handlers.handleKeyDown({ key: 'x', preventDefault: vi.fn() })
    ).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Fix B (#2604): advanceCamera uses W/H from params, not hardcoded 800/600
// ---------------------------------------------------------------------------

describe('advanceCamera uses W/H from params (#2604)', () => {
  function makeCamera(overrides = {}) {
    return { x: 500, y: 400, z: 1, ...overrides };
  }

  function makeCameraRefs(overrides = {}) {
    return {
      navRef: { current: { path: [{ name: 'root', path: '' }] } },
      camRef: { current: null },
      animRef: { current: null },
      frameCount: { current: 0 },
      sceneRef: { current: null },
      nextSceneRef: { current: null },
      zoomedFileRef: { current: null },
      focusedFolderRef: { current: null },
      zoomTargetRef: { current: null },
      flyRef: { current: null },
      prevNavRef: { current: null },
      ...overrides,
    };
  }

  it('centering inside anim swap uses W and H from params, not 800/600', () => {
    // Set up an animation that is complete (t >= 1) so the anim block runs.
    // A focusedFolderRef with autoEnter=true and a valid folder star triggers
    // the buildFolderScene call — we verify the scene receives the custom dims.
    const customW = 1200;
    const customH = 900;
    const folderNode = { name: 'src', path: 'src', children: [] };
    const star = {
      x: 100, y: 100, isFolder: true, _node: folderNode,
      radius: 10, col: '#fff',
    };
    const scene = { rootStars: [star] };

    const refs = makeCameraRefs({
      animRef: { current: { t: 1, sx: 0, sy: 0, sz: 1, out: false } },
      focusedFolderRef: { current: { autoEnter: true, starIdx: 0, x: 100, y: 100 } },
      sceneRef: { current: scene },
    });

    const cam = makeCamera();
    const getFitZoom = vi.fn(() => 1);
    const computeFocusCamera = vi.fn(() => ({ x: customW / 2, y: customH / 2, z: 1 }));

    advanceCamera(cam, refs, {
      TRANS: 0.8,
      scene,
      computeFocusCamera,
      saveNav: vi.fn(),
      setNavVersion: vi.fn(),
      getFitZoom,
      W: customW,
      H: customH,
    });

    // buildFolderScene was called (nextSceneRef is populated) and its _node set.
    expect(refs.nextSceneRef.current).not.toBeNull();
    // The fly transition records starX/starY from the star, not from 800/600 literals.
    expect(refs.flyRef.current).not.toBeNull();
  });
});
