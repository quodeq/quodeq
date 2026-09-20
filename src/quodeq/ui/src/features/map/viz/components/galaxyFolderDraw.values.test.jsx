/**
 * Value-level characterization for the parts of galaxyFolderDraw the nebula
 * snapshots do not reach: the starfield alphas, the constellation strokes,
 * the per-star glow/particle scales, the labeled violation orbs, the label
 * placement and its collision margins, and the hit-test radii.
 *
 * galaxyFolderDraw.test.jsx records only WHICH ctx methods fire; this one
 * records every argument and style write, so the tuning constants extracted
 * from this module are checked against the exact pixels.
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
    scoreRGB: () => col,
    rgba: (c, a) => `rgba(${c.r},${c.g},${c.b},${round(a)})`,
    drawGlow: (_ctx, a) => rec.log.push(['drawGlow', roundAll({ x: a.x, y: a.y, r: a.r, alpha: a.alpha })]),
    drawParticles: (_ctx, ps, a) => rec.log.push(['drawParticles', ps.length, roundAll({ cx: a.cx, cy: a.cy, scale: a.scale, alpha: a.alpha, drawScale: a.drawScale })]),
  };
});

import {
  drawScene, drawStarfield, drawConstellationLines, drawStars, drawLabels,
} from './galaxyFolderDraw.js';

/** A 2D context that appends every call and every style write to `log`. */
function makeRecordingCtx(log) {
  const methods = [
    'fillRect', 'beginPath', 'arc', 'fill', 'moveTo', 'lineTo',
    'stroke', 'setLineDash', 'fillText',
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

const COL = { r: 100, g: 150, b: 200 };

function makeFolderStar(extra) {
  return {
    name: 'src/deep', isFolder: true, x: 400, y: 300, radius: 20, col: COL,
    pp: 0, violations: 3, complianceRate: 0.5,
    particles: [{ col: COL, sev: 'critical', or: 30, os: 1, op: 0, sz: 3, ec: 0.8, tp: 0 }],
    ...extra,
  };
}

function makeFileStar(extra) {
  return {
    name: 'index.js', isFolder: false, x: 500, y: 350, radius: 8, col: COL,
    pp: 0.5, violations: 0, complianceRate: 0.5,
    particles: [
      { col: COL, sev: 'major', or: 15, os: 1, op: 0, sz: 2, ec: 1, tp: 0 },
      { col: COL, sev: 'minor', or: 22, os: -1, op: 1, sz: 4, ec: 0.9, tp: 2 },
    ],
    ...extra,
  };
}

function makeScene() {
  return {
    rootStars: [makeFolderStar(), makeFileStar()],
    lines: [{ a: 0, b: 1 }],
    bg: [{ x: 0.5, y: 0.5, sz: 1, sp: 0.5, tw: 0 }, { x: 0.2, y: 0.8, sz: 0.4, sp: 0.9, tw: 1 }],
  };
}

const w2s = (wx, wy) => ({ x: wx, y: wy });
const TC = { text: COL, textMuted: COL };

function drawParams(extra) {
  return {
    t: 7, cam: { x: 0, y: 0, z: 3 }, w2s, showLabels: true,
    mouseRef: { current: { x: -1, y: -1 } }, flyRef: { current: null },
    focusedFolderRef: { current: null }, animRef: { current: null }, tc: TC,
    ...extra,
  };
}

describe('galaxyFolderDraw value characterization', () => {
  beforeEach(() => { rec.log = []; });

  it('drawScene paints the background gradient at the recorded radius', () => {
    const ctx = makeRecordingCtx(rec.log);
    drawScene(ctx, makeScene(), { W: 800, H: 600, canvasRef: { current: null } });
    expect(rec.log).toMatchSnapshot('scene-background-values');
  });

  it('drawStarfield twinkles each background star between its recorded alphas', () => {
    const ctx = makeRecordingCtx(rec.log);
    drawStarfield(ctx, makeScene().bg, TC, { W: 800, H: 600, t: 7 });
    expect(rec.log).toMatchSnapshot('starfield-values');
  });

  it('drawConstellationLines strokes at the recorded alpha and width', () => {
    const ctx = makeRecordingCtx(rec.log);
    drawConstellationLines(ctx, makeScene(), TC, w2s);
    expect(rec.log).toMatchSnapshot('constellation-line-values');
  });

  it('drawStars at cam.z=3: folder nebula, particles, labeled orbs, labels', () => {
    const ctx = makeRecordingCtx(rec.log);
    const { pendingLabels } = drawStars(ctx, makeScene(), drawParams());
    expect(pendingLabels.map((l) => roundAll({
      fs: l.fs, fontSize: l.fontSize, lx: l.lx, ly: l.ly, lw: l.lw, lh: l.lh, importance: l.importance,
    }))).toMatchSnapshot('pending-label-geometry');
    expect(rec.log).toMatchSnapshot('draw-stars-zoomed-values');
  });

  it('drawStars at cam.z=1 keeps the zoomed-out nebula, border ring and no orbs', () => {
    const ctx = makeRecordingCtx(rec.log);
    drawStars(ctx, makeScene(), drawParams({ cam: { x: 0, y: 0, z: 1 } }));
    expect(rec.log).toMatchSnapshot('draw-stars-zoomed-out-values');
  });

  it('drawStars dims a folder star once its screen radius passes the threshold', () => {
    const ctx = makeRecordingCtx(rec.log);
    const scene = { ...makeScene(), rootStars: [makeFolderStar({ radius: 60 })], lines: [] };
    drawStars(ctx, scene, drawParams({ cam: { x: 0, y: 0, z: 4 } }));
    expect(rec.log).toMatchSnapshot('draw-stars-dimmed-folder-values');
  });

  it('drawStars fades the folder nebula while flying into it', () => {
    const ctx = makeRecordingCtx(rec.log);
    drawStars(ctx, makeScene(), drawParams({
      flyRef: { current: { reverse: false, swapped: false, dimStarIdx: 0, t: 0.2 } },
    }));
    expect(rec.log).toMatchSnapshot('draw-stars-flying-values');
  });

  it('drawStars hit-tests the star radius and the folder cluster radius', () => {
    const ctx = makeRecordingCtx(rec.log);
    const scene = makeScene();
    // Inside the dashed cluster border but outside the star itself.
    const hitFar = drawStars(ctx, scene, drawParams({
      cam: { x: 0, y: 0, z: 1 }, mouseRef: { current: { x: 400 + 30, y: 300 } },
    }));
    expect(hitFar.newHovered).toMatchObject({ type: 'folder', starIdx: 0 });
    const hitFile = drawStars(ctx, scene, drawParams({
      cam: { x: 0, y: 0, z: 1 }, mouseRef: { current: { x: 505, y: 350 } },
    }));
    expect(hitFile.newHovered).toMatchObject({ type: 'file', starIdx: 1 });
  });

  it('drawLabels places by importance and skips colliding boxes', () => {
    const ctx = makeRecordingCtx(rec.log);
    const folder = makeFolderStar();
    const file = makeFileStar({ violations: 4 });
    const mk = (s, over) => ({
      s, sc: { x: s.x, y: s.y }, sr: 12, fs: 1.5, label: s.name,
      fontSize: 16.5, lx: s.x, ly: s.y - 30, lw: 40, lh: 20, importance: 1003, col: s.col, ...over,
    });
    drawLabels(ctx, [
      mk(folder),
      mk(file, { importance: 4, lx: 500, ly: 320 }),
      // Overlaps the first label's box, so it must be dropped.
      mk(folder, { importance: 2, lx: 404, ly: 272 }),
    ], TC);
    expect(rec.log).toMatchSnapshot('draw-labels-values');
  });
});
