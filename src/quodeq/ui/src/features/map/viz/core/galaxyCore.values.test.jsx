/**
 * Value-level characterization for galaxyCore's drawing and particle math:
 * drawGlow's gradient radii and alpha stops, drawParticles' orbit/twinkle
 * numbers, mkParticles' orbit/speed/size/eccentricity ranges, seedHash's
 * mixing constant and gradeToScore's fallback.
 *
 * parseCSSColor/getThemeColors need a real 2D context, which JSDOM does not
 * provide (vitest.setup.js stubs getContext to null); the two tests that
 * reach them stub a minimal context, and Math.random is made deterministic
 * so the particle ranges snapshot stably.
 *
 * Captured from the pre-naming code — keep the snapshots unchanged.
 */
import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import {
  drawGlow, drawParticles, mkParticles, seedHash, seededRng, gradeToScore,
} from './galaxyCore.js';

let originalGetContext;
beforeAll(() => {
  originalGetContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function stubGetContext() {
    return {
      clearRect: () => {}, fillRect: () => {}, fillStyle: '',
      getImageData: () => ({ data: [128, 128, 128, 255] }),
    };
  };
});
afterAll(() => { HTMLCanvasElement.prototype.getContext = originalGetContext; });

const round = (n) => (typeof n === 'number' ? Number(n.toFixed(6)) : n);

/** A 2D context that appends every call and every style write to `log`. */
function makeRecordingCtx(log) {
  const target = {};
  for (const m of ['beginPath', 'arc', 'fill', 'stroke']) {
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

describe('galaxyCore drawGlow', () => {
  it('paints the outer and core gradients at the recorded radii and alphas', () => {
    const log = [];
    drawGlow(makeRecordingCtx(log), { x: 100, y: 200, r: 6, col: COL, alpha: 0.8 });
    expect(log).toMatchSnapshot('glow-values');
  });

  it('skips a glow below the minimum radius or alpha', () => {
    const log = [];
    drawGlow(makeRecordingCtx(log), { x: 0, y: 0, r: 0.29, col: COL, alpha: 1 });
    drawGlow(makeRecordingCtx(log), { x: 0, y: 0, r: 5, col: COL, alpha: 0.009 });
    expect(log).toEqual([]);
    // Just above each floor it draws.
    drawGlow(makeRecordingCtx(log), { x: 0, y: 0, r: 0.3, col: COL, alpha: 0.01 });
    expect(log.length).toBeGreaterThan(0);
  });
});

describe('galaxyCore drawParticles', () => {
  it('orbits, twinkles and sizes each particle by the recorded factors', () => {
    const log = [];
    const particles = [
      { col: COL, or: 30, os: 1, op: 0, sz: 3, ec: 0.8, tp: 0 },
      { col: COL, or: 18, os: -0.5, op: 1.2, sz: 1.5, ec: 1, tp: 2 },
    ];
    drawParticles(makeRecordingCtx(log), particles, {
      cx: 100, cy: 200, scale: 2, alpha: 0.7, t: 5, drawScale: 1.5,
    });
    expect(log).toMatchSnapshot('particles-values');
  });

  it('drops a particle whose drawn size falls under the floor', () => {
    const log = [];
    drawParticles(makeRecordingCtx(log), [{ col: COL, or: 10, os: 1, op: 0, sz: 1, ec: 1, tp: 0 }], {
      cx: 0, cy: 0, scale: 1, alpha: 1, t: 0, drawScale: 0.149,
    });
    expect(log).toEqual([]);
  });

  it('falls back to `scale` when no drawScale is given', () => {
    const withDraw = [];
    const withoutDraw = [];
    const p = [{ col: COL, or: 10, os: 1, op: 0, sz: 2, ec: 1, tp: 0 }];
    drawParticles(makeRecordingCtx(withDraw), p, { cx: 0, cy: 0, scale: 3, alpha: 1, t: 1, drawScale: 3 });
    drawParticles(makeRecordingCtx(withoutDraw), p, { cx: 0, cy: 0, scale: 3, alpha: 1, t: 1 });
    expect(withoutDraw).toEqual(withDraw);
  });
});

describe('galaxyCore mkParticles', () => {
  let randomSpy;
  beforeEach(() => {
    let i = 0;
    // A deterministic stand-in for Math.random that still walks the 0..1
    // range, so every `base + random() * range` lands on a distinct value.
    randomSpy = vi.spyOn(Math, 'random').mockImplementation(() => ((i++ * 7) % 11) / 11);
  });
  afterEach(() => { randomSpy.mockRestore(); });

  it('builds orbit, speed, size and eccentricity from the recorded ranges', () => {
    const ps = mkParticles(2, 1, 1, 12);
    expect(ps.map((p) => ({
      sev: p.sev, or: round(p.or), os: round(p.os), op: round(p.op),
      sz: round(p.sz), ec: round(p.ec), tp: round(p.tp),
    }))).toMatchSnapshot('mk-particles-values');
  });

  it('caps each severity at the per-severity particle maximum', () => {
    expect(mkParticles(50, 0, 0, 5)).toHaveLength(10);
    expect(mkParticles(50, 50, 50, 5)).toHaveLength(30);
  });
});

describe('galaxyCore seeded helpers', () => {
  it('seedHash mixes with the recorded shift', () => {
    expect([seedHash(''), seedHash('a'), seedHash('galaxy:clean|solid')]).toMatchSnapshot('seed-hash-values');
  });

  it('seededRng walks the recorded LCG sequence', () => {
    const rng = seededRng(seedHash('cl:builtin'));
    expect(Array.from({ length: 6 }, () => round(rng()))).toMatchSnapshot('seeded-rng-values');
  });

  it('gradeToScore maps every grade and falls back for an unknown one', () => {
    expect(['A', 'B', 'C', 'D', 'F', 'Z', undefined].map(gradeToScore))
      .toMatchSnapshot('grade-to-score-values');
  });
});
