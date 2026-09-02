/**
 * Characterization test for galaxyFolderDraw.js — written BEFORE drawStars is
 * split into drawFolderNebula/drawFileParticles/drawLabeledOrbs/
 * collectStarLabel/hitTestStar, so the refactor can be checked against a
 * captured baseline instead of eyeballing a canvas. Mirrors the strategy in
 * galaxyViewDraw.test.jsx: mock galaxyCore's DOM-dependent color/theme
 * helpers, record every ctx method call in order, and snapshot the sequence.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { drawScene, drawNebula, drawStarfield, drawConstellationLines, drawStars, drawLabels } from './galaxyFolderDraw.js';

vi.mock('../core/galaxyCore.js', () => {
  const col = { r: 100, g: 150, b: 200 };
  return {
    TAU: Math.PI * 2,
    getThemeColors: vi.fn(() => ({ bg: '#000', bgAlt: '#111', text: col, textMuted: col })),
    scoreRGB: vi.fn(() => col),
    rgba: vi.fn((c, a) => `rgba(${c.r},${c.g},${c.b},${a})`),
    drawGlow: vi.fn(),
    drawParticles: vi.fn(),
  };
});

function makeMockCtx(calls) {
  const methods = [
    'createRadialGradient', 'fillRect', 'beginPath', 'arc', 'fill',
    'moveTo', 'lineTo', 'stroke', 'setLineDash', 'fillText',
  ];
  const ctx = { fillStyle: null, strokeStyle: null, lineWidth: null, font: null, textAlign: null };
  for (const m of methods) {
    ctx[m] = vi.fn((...args) => {
      calls.push(m);
      if (m === 'createRadialGradient') return { addColorStop: vi.fn() };
    });
  }
  return ctx;
}

function makeFolderStar() {
  const col = { r: 100, g: 150, b: 200 };
  return {
    name: 'src', isFolder: true, x: 400, y: 300, radius: 20, col,
    pp: 0, violations: 3, complianceRate: 0.5,
    particles: [{ col, sev: 'critical', or: 30, os: 1, op: 0, sz: 3, ec: 1, tp: 0 }],
  };
}

function makeFileStar() {
  const col = { r: 100, g: 150, b: 200 };
  return {
    name: 'index.js', isFolder: false, x: 500, y: 350, radius: 8, col,
    pp: 0, violations: 2, complianceRate: 0.5,
    particles: [{ col, sev: 'major', or: 15, os: 1, op: 0, sz: 2, ec: 1, tp: 0 }],
  };
}

function makeScene() {
  const folder = makeFolderStar();
  const file = makeFileStar();
  return { rootStars: [folder, file], lines: [{ a: 0, b: 1 }], bg: [{ x: 0.5, y: 0.5, sz: 1, sp: 0.5, tw: 0 }] };
}

function makeW2s() {
  return (wx, wy) => ({ x: wx, y: wy });
}

function makeRefs() {
  return {
    canvasRef: { current: { parentElement: null } },
    mouseRef: { current: { x: -1, y: -1 } },
    flyRef: { current: null },
    focusedFolderRef: { current: null },
    animRef: { current: null },
  };
}

describe('galaxyFolderDraw smoke coverage (pre-refactor baseline)', () => {
  let calls;

  beforeEach(() => {
    calls = [];
    vi.clearAllMocks();
  });

  it('drawScene fills the background and returns theme colors', () => {
    const ctx = makeMockCtx(calls);
    const refs = makeRefs();
    const { tc } = drawScene(ctx, makeScene(), {
      W: 800, H: 600, t: 0, cam: { x: 0, y: 0, z: 1 }, w2s: makeW2s(),
      showLabels: true, mouseRef: refs.mouseRef, flyRef: refs.flyRef,
      focusedFolderRef: refs.focusedFolderRef, canvasRef: refs.canvasRef,
    });
    expect(tc).toBeTruthy();
    expect(calls).toContain('createRadialGradient');
    expect(calls).toContain('fillRect');
  });

  it('drawNebula, drawStarfield, drawConstellationLines do not throw and touch the ctx', () => {
    const ctx = makeMockCtx(calls);
    const scene = makeScene();
    const tc = { text: { r: 1, g: 1, b: 1 }, textMuted: { r: 1, g: 1, b: 1 } };
    expect(() => drawNebula(ctx, scene.rootStars[0], tc, 800, 600, 0)).not.toThrow();
    expect(() => drawStarfield(ctx, scene.bg, tc, 800, 600, 0)).not.toThrow();
    expect(() => drawConstellationLines(ctx, scene, tc, makeW2s())).not.toThrow();
    expect(calls.length).toBeGreaterThan(0);
  });

  it('drawStars records the ctx-call sequence for a folder + file star (order-preserving refactor guard)', () => {
    const ctx = makeMockCtx(calls);
    const scene = makeScene();
    const tc = { text: { r: 1, g: 1, b: 1 }, textMuted: { r: 1, g: 1, b: 1 } };
    const { pendingLabels, newHovered } = drawStars(ctx, scene, {
      t: 0, cam: { x: 0, y: 0, z: 3 }, w2s: makeW2s(), showLabels: true,
      mouseRef: { current: { x: -1, y: -1 } }, flyRef: { current: null },
      focusedFolderRef: { current: null }, animRef: { current: null }, tc,
    });
    expect(Array.isArray(pendingLabels)).toBe(true);
    expect(pendingLabels.length).toBe(2);
    expect(newHovered).toBeNull();
    expect(calls).toMatchSnapshot('folder-plus-file-star-ctx-calls');
  });

  it('drawStars hit-tests the star under the mouse when idle', () => {
    const ctx = makeMockCtx(calls);
    const scene = makeScene();
    const tc = { text: { r: 1, g: 1, b: 1 }, textMuted: { r: 1, g: 1, b: 1 } };
    const { newHovered } = drawStars(ctx, scene, {
      t: 0, cam: { x: 0, y: 0, z: 1 }, w2s: makeW2s(), showLabels: false,
      mouseRef: { current: { x: 400, y: 300 } }, flyRef: { current: null },
      focusedFolderRef: { current: null }, animRef: { current: null }, tc,
    });
    expect(newHovered).not.toBeNull();
    expect(newHovered.type).toBe('folder');
  });

  it('drawLabels does not throw for collected labels', () => {
    const ctx = makeMockCtx(calls);
    const tc = { text: { r: 1, g: 1, b: 1 }, textMuted: { r: 1, g: 1, b: 1 } };
    const folder = makeFolderStar();
    const label = {
      s: folder, sc: { x: 400, y: 300 }, sr: 20, fs: 1, label: 'src',
      fontSize: 11, lx: 400, ly: 260, lw: 40, lh: 15, importance: 1003, col: folder.col,
    };
    expect(() => drawLabels(ctx, [label], tc)).not.toThrow();
    expect(calls).toContain('fillText');
  });
});
