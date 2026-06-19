/**
 * Characterization test for drawFrame — locks the sequence of canvas-context
 * method calls so behavior-preserving refactors can be verified.
 *
 * Strategy:
 *  - Mock getThemeColors, drawGlow, drawParticles (they have their own DOM
 *    dependencies and their own tests).
 *  - Build a minimal scene covering every rendering branch (background stars,
 *    constellations at cam.z < 3, dim stars, principle planets, zoomed orbs).
 *  - Record the name of every ctx method call in order.
 *  - Assert the sequence matches a captured snapshot so a refactor that moves
 *    code into helpers must produce the IDENTICAL call sequence.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { drawFrame } from './galaxyViewDraw.js';

// Mock galaxyCore to avoid DOM dependencies and to record drawGlow/drawParticles
vi.mock('../core/galaxyCore.js', () => {
  const col = { r: 100, g: 150, b: 200 };
  return {
    TAU: Math.PI * 2,
    getThemeColors: vi.fn(() => ({
      bg: '#000',
      bgAlt: '#111',
      text: col,
      textMuted: col,
    })),
    drawGlow: vi.fn(),
    drawParticles: vi.fn(),
    rgba: vi.fn((c, a) => `rgba(${c.r},${c.g},${c.b},${a})`),
    rgb: vi.fn((c) => `rgb(${c.r},${c.g},${c.b})`),
  };
});

function makeMockCtx(calls) {
  const methods = [
    'createRadialGradient', 'fillRect', 'beginPath', 'arc', 'fill',
    'moveTo', 'lineTo', 'stroke', 'setLineDash', 'fillText',
  ];
  const ctx = {
    fillStyle: null,
    strokeStyle: null,
    lineWidth: null,
    font: null,
    textAlign: null,
    createRadialGradient: vi.fn(() => ({
      addColorStop: vi.fn(),
    })),
  };
  for (const m of methods.filter(m => m !== 'createRadialGradient')) {
    ctx[m] = vi.fn((...args) => { calls.push(m); });
  }
  // Record createRadialGradient too
  const origCRG = ctx.createRadialGradient;
  ctx.createRadialGradient = vi.fn((...args) => { calls.push('createRadialGradient'); return origCRG(...args); });
  return ctx;
}

function makeScene() {
  const col = { r: 100, g: 150, b: 200 };
  const particle = { os: 1, op: 0, or: 30, ec: 1, sz: 2, tp: 0, col, sev: 'minor' };
  // Dim particle (on the star itself)
  const dimParticle = { os: 0.5, op: 0, or: 20, ec: 1, sz: 1.5, tp: 0, col };
  const principle = {
    x: 450, y: 320, radius: 10, col, name: 'P1', score: 7.5,
    particles: [particle],
    dimParticle,
  };
  const star = {
    x: 400, y: 300, radius: 20, col, name: 'Dim1', score: 7.0,
    pp: 0, sp: 0.1, tw: 0,
    _clusterCx: 50, _clusterCy: 50,
  };
  const bgStar = { x: 0.5, y: 0.5, sz: 1, sp: 0.5, tw: 0 };
  const constellation = {
    cx: 50, cy: 50, spread: 80, label: 'Constellation A',
    lines: [{ a: 0, b: 0 }],
  };
  return {
    bg: [bgStar],
    constellations: [constellation],
    stars: [star],
    principles: [[principle]],
  };
}

function makeW2s() {
  return (wx, wy) => ({ x: wx, y: wy });
}

describe('drawFrame characterization (#950)', () => {
  let calls;

  beforeEach(() => {
    calls = [];
    vi.clearAllMocks();
  });

  it('galaxy level (cam.z=1) — records ctx-call sequence', () => {
    const ctx = makeMockCtx(calls);
    const scene = makeScene();
    const cam = { x: 0, y: 0, z: 1 };
    const nav = { depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null };
    const opts = {
      W: 800, H: 600, t: 0, mx: -1, my: -1,
      showLabels: true, animating: false, rDim: null, rPrin: null,
      w2s: makeW2s(), parentEl: null,
    };
    const result = drawFrame(ctx, scene, cam, nav, opts);
    expect(result).toHaveProperty('hovered');
    // Snapshot the call sequence
    expect(calls).toMatchSnapshot('galaxy-level-ctx-calls');
  });

  it('zoomed into dimension (cam.z=5, rDim=0) — records ctx-call sequence', () => {
    const ctx = makeMockCtx(calls);
    const scene = makeScene();
    const cam = { x: 0, y: 0, z: 5 };
    const nav = { depth: 1, dim: 0, prin: null, clusterCx: null, clusterCy: null };
    const opts = {
      W: 800, H: 600, t: 0, mx: -1, my: -1,
      showLabels: true, animating: false, rDim: 0, rPrin: null,
      w2s: makeW2s(), parentEl: null,
    };
    const result = drawFrame(ctx, scene, cam, nav, opts);
    expect(result).toHaveProperty('hovered');
    expect(calls).toMatchSnapshot('zoomed-dim-ctx-calls');
  });

  it('zoomed into principle (cam.z=15, rDim=0, rPrin=0) — records ctx-call sequence', () => {
    const ctx = makeMockCtx(calls);
    const scene = makeScene();
    const cam = { x: 0, y: 0, z: 15 };
    const nav = { depth: 2, dim: 0, prin: 0, clusterCx: null, clusterCy: null };
    const opts = {
      W: 800, H: 600, t: 0, mx: -1, my: -1,
      showLabels: true, animating: false, rDim: 0, rPrin: 0,
      w2s: makeW2s(), parentEl: null,
    };
    const result = drawFrame(ctx, scene, cam, nav, opts);
    expect(result).toHaveProperty('hovered');
    expect(calls).toMatchSnapshot('zoomed-principle-ctx-calls');
  });
});
