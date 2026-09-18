/**
 * Accessibility tests for the galaxy folder draw module.
 * 6423: particle severity was encoded in colour only (the severity text
 * shows up at high zoom with labels on). starShapeFor adds a shape cue that
 * is always drawn: critical a ring plus a core dot, major a ring, minor the
 * plain dot. The pure function is tested directly; the draw routine is
 * checked through a recording ctx, so no canvas is needed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { drawStars, starShapeFor } from './galaxyFolderDraw.js';

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

const COL = { r: 100, g: 150, b: 200 };

function makeMockCtx(calls) {
  const methods = ['createRadialGradient', 'fillRect', 'beginPath', 'arc', 'fill', 'moveTo', 'lineTo', 'stroke', 'setLineDash', 'fillText'];
  const ctx = { fillStyle: null, strokeStyle: null, lineWidth: null, font: null, textAlign: null };
  for (const m of methods) {
    ctx[m] = vi.fn(() => {
      calls.push(m);
      if (m === 'createRadialGradient') return { addColorStop: vi.fn() };
    });
  }
  return ctx;
}

function fileStarWith(severities) {
  return {
    name: 'index.js', isFolder: false, x: 100, y: 100, radius: 8, col: COL,
    pp: 0, violations: severities.length, complianceRate: 0.5,
    particles: severities.map((sev) => ({ col: COL, sev, or: 15, os: 1, op: 0, sz: 3, ec: 1, tp: 0 })),
  };
}

function runDrawStars(ctx, star) {
  return drawStars(ctx, { rootStars: [star], lines: [], bg: [] }, {
    t: 0, cam: { x: 0, y: 0, z: 1 }, w2s: (x, y) => ({ x, y }), showLabels: false,
    mouseRef: { current: { x: -1, y: -1 } }, flyRef: { current: null },
    focusedFolderRef: { current: null }, animRef: { current: null },
    tc: { text: COL, textMuted: COL },
  });
}

describe('starShapeFor (6423)', () => {
  it('maps each severity to its own shape', () => {
    expect(starShapeFor('critical')).toBe('ring-dot');
    expect(starShapeFor('major')).toBe('ring');
    expect(starShapeFor('minor')).toBe('dot');
  });

  it('falls back to the plain dot for an unknown or missing severity', () => {
    expect(starShapeFor('info')).toBe('dot');
    expect(starShapeFor(undefined)).toBe('dot');
  });

  it('gives critical and major distinct shapes', () => {
    expect(starShapeFor('critical')).not.toBe(starShapeFor('major'));
    expect(starShapeFor('major')).not.toBe(starShapeFor('minor'));
  });
});

describe('galaxy particle shape cue (6423)', () => {
  let calls;
  beforeEach(() => { calls = []; vi.clearAllMocks(); });

  it('strokes a ring for a major particle at plain zoom with labels off', () => {
    const ctx = makeMockCtx(calls);
    runDrawStars(ctx, fileStarWith(['major']));
    expect(calls.filter((c) => c === 'stroke').length).toBe(1);
  });

  it('adds a filled core dot on top of the ring for a critical particle', () => {
    const ctx = makeMockCtx(calls);
    runDrawStars(ctx, fileStarWith(['critical']));
    expect(calls.filter((c) => c === 'stroke').length).toBe(1);
    expect(calls.filter((c) => c === 'fill').length).toBe(1);
  });

  it('leaves a minor particle as the plain dot drawParticles paints', () => {
    const ctx = makeMockCtx(calls);
    runDrawStars(ctx, fileStarWith(['minor']));
    expect(calls).not.toContain('stroke');
    expect(calls).not.toContain('fill');
  });
});
