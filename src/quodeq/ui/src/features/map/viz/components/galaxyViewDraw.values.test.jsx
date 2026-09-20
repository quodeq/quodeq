/**
 * Value-level characterization for galaxyViewDraw. The sibling
 * galaxyViewDraw.test.jsx records only WHICH ctx methods fire; this one
 * records every argument, every style write and every drawGlow/drawParticles
 * payload, so the tuning constants extracted from this module are checked
 * against the exact pixels the literals produced.
 *
 * Captured from the pre-naming code — keep the snapshots unchanged.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const rec = vi.hoisted(() => ({ log: [] }));

const round = (n) => (typeof n === 'number' ? Number(n.toFixed(6)) : n);
const roundAll = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, round(v)]));

vi.mock('../core/galaxyCore.js', () => {
  const col = { r: 100, g: 150, b: 200 };
  return {
    TAU: Math.PI * 2,
    getThemeColors: () => ({ bg: '#000', bgAlt: '#111', text: col, textMuted: col }),
    drawGlow: (_ctx, a) => rec.log.push(['drawGlow', roundAll({ x: a.x, y: a.y, r: a.r, alpha: a.alpha })]),
    drawParticles: (_ctx, ps, a) => rec.log.push(['drawParticles', ps.length, roundAll({ cx: a.cx, cy: a.cy, scale: a.scale, alpha: a.alpha, drawScale: a.drawScale })]),
    rgba: (c, a) => `rgba(${c.r},${c.g},${c.b},${round(a)})`,
    rgb: (c) => `rgb(${c.r},${c.g},${c.b})`,
  };
});

import { drawFrame } from './galaxyViewDraw.js';

/** A 2D context that appends every call and every style write to `log`. */
function makeRecordingCtx(log) {
  const methods = [
    'fillRect', 'beginPath', 'arc', 'fill', 'moveTo', 'lineTo',
    'stroke', 'setLineDash', 'fillText', 'save', 'restore',
  ];
  const target = {};
  for (const m of methods) {
    target[m] = (...args) => { log.push([m, ...args.map(round)]); };
  }
  target.createRadialGradient = (...args) => {
    log.push(['createRadialGradient', ...args.map(round)]);
    return { addColorStop: (offset, color) => log.push(['stop', round(offset), color]) };
  };
  return new Proxy(target, {
    set(t, prop, value) { log.push(['=' + String(prop), round(value)]); t[prop] = value; return true; },
  });
}

function makeScene() {
  const col = { r: 100, g: 150, b: 200 };
  const particle = { os: 1, op: 0, or: 30, ec: 1, sz: 2, tp: 0, col, sev: 'critical' };
  const dimParticle = { os: 0.5, op: 0, or: 20, ec: 1, sz: 1.5, tp: 0, col };
  const principle = {
    x: 450, y: 320, radius: 10, col, name: 'P1', score: 7.5,
    particles: [particle, { ...particle, sev: 'major', or: 18 }],
    dimParticle,
  };
  const star = {
    x: 400, y: 300, radius: 20, col, name: 'Dim1', score: 7,
    pp: 0, sp: 0.1, tw: 0, _clusterCx: 50, _clusterCy: 50,
  };
  return {
    bg: [{ x: 0.5, y: 0.5, sz: 1, sp: 0.5, tw: 0 }, { x: 0.25, y: 0.75, sz: 0.4, sp: 0.9, tw: 1 }],
    constellations: [{ cx: 50, cy: 50, spread: 80, label: 'Constellation A', lines: [{ a: 0, b: 0 }] }],
    stars: [star],
    principles: [[principle]],
  };
}

const w2s = (wx, wy) => ({ x: wx, y: wy });

function baseOpts(extra) {
  return {
    W: 800, H: 600, t: 3.5, mx: -1, my: -1,
    showLabels: true, animating: false, rDim: null, rPrin: null,
    w2s, parentEl: null, focusedIdx: null, ...extra,
  };
}

describe('galaxyViewDraw value characterization', () => {
  beforeEach(() => { rec.log = []; });

  it('galaxy level (cam.z=1): background, constellations, dim star + particles', () => {
    const ctx = makeRecordingCtx(rec.log);
    drawFrame(ctx, makeScene(), { x: 0, y: 0, z: 1 },
      { depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null }, baseOpts());
    expect(rec.log).toMatchSnapshot('galaxy-level-values');
  });

  it('galaxy level with an unfocused cluster dims the constellation and the star', () => {
    const ctx = makeRecordingCtx(rec.log);
    drawFrame(ctx, makeScene(), { x: 0, y: 0, z: 2.4 },
      { depth: 0, dim: null, prin: null, clusterCx: 999, clusterCy: 999 }, baseOpts());
    expect(rec.log).toMatchSnapshot('galaxy-level-unfocused-cluster-values');
  });

  it('galaxy level draws the keyboard focus ring and hit-tests the star under the mouse', () => {
    const ctx = makeRecordingCtx(rec.log);
    const { hovered } = drawFrame(ctx, makeScene(), { x: 0, y: 0, z: 1 },
      { depth: 0, dim: null, prin: null, clusterCx: null, clusterCy: null },
      baseOpts({ mx: 400, my: 300, focusedIdx: 0 }));
    expect(hovered).toEqual({ type: 'dim', idx: 0, data: expect.objectContaining({ name: 'Dim1' }) });
    expect(rec.log).toMatchSnapshot('galaxy-level-focus-ring-values');
  });

  it('zoomed into a dimension (cam.z=5): principle planets, orbit rings and labels', () => {
    const ctx = makeRecordingCtx(rec.log);
    const { hovered } = drawFrame(ctx, makeScene(), { x: 0, y: 0, z: 5 },
      { depth: 1, dim: 0, prin: null, clusterCx: null, clusterCy: null },
      baseOpts({ rDim: 0, mx: 450, my: 320, focusedIdx: 0 }));
    expect(hovered).toEqual({ type: 'prin', idx: 0, data: expect.objectContaining({ name: 'P1' }) });
    expect(rec.log).toMatchSnapshot('zoomed-dim-values');
  });

  it('zoomed into a principle (cam.z=15): sibling fade plus the violation orbs', () => {
    const ctx = makeRecordingCtx(rec.log);
    drawFrame(ctx, makeScene(), { x: 0, y: 0, z: 15 },
      { depth: 2, dim: 0, prin: 0, clusterCx: null, clusterCy: null },
      baseOpts({ rDim: 0, rPrin: 0 }));
    expect(rec.log).toMatchSnapshot('zoomed-principle-values');
  });

  it('deep zoom (cam.z=40) past the principle fade span', () => {
    const ctx = makeRecordingCtx(rec.log);
    const scene = makeScene();
    scene.principles[0].push({ ...scene.principles[0][0], x: 470, y: 340, name: 'P2' });
    drawFrame(ctx, scene, { x: 0, y: 0, z: 40 },
      { depth: 2, dim: 0, prin: 0, clusterCx: null, clusterCy: null },
      baseOpts({ rDim: 0, rPrin: 0 }));
    expect(rec.log).toMatchSnapshot('deep-zoom-values');
  });
});
