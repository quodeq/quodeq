/**
 * Value-level characterization for the two nebulas galaxyFolderDraw paints —
 * the scene-wide one (drawNebula) and a folder cluster's (drawStars →
 * drawFolderNebula). The sibling smoke test only records which ctx methods
 * fire; this one snapshots the gradient geometry and colour stops, so the
 * shared blob helper can be checked against the exact discs it replaced.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { drawNebula, drawStars } from './galaxyFolderDraw.js';

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

const round = (n) => (typeof n === 'number' ? Number(n.toFixed(6)) : n);

// Records every radial gradient as { from: [args], stops: [[offset, color]] }
// plus the arc it is filled through, which is what the blob loops produce.
function makeRecordingCtx(discs) {
  const ctx = { fillStyle: null, strokeStyle: null, lineWidth: null, font: null, textAlign: null };
  const noop = ['fillRect', 'beginPath', 'moveTo', 'lineTo', 'stroke', 'setLineDash', 'fillText'];
  for (const m of noop) ctx[m] = vi.fn();
  ctx.createRadialGradient = vi.fn((...args) => {
    const disc = { gradient: args.map(round), stops: [], arc: null };
    discs.push(disc);
    return { addColorStop: (offset, color) => disc.stops.push([round(offset), color]) };
  });
  ctx.arc = vi.fn((...args) => {
    const last = discs[discs.length - 1];
    if (last && last.arc === null) last.arc = args.map(round);
  });
  ctx.fill = vi.fn();
  return ctx;
}

function makeFolderStar() {
  const col = { r: 100, g: 150, b: 200 };
  return {
    name: 'src', isFolder: true, x: 400, y: 300, radius: 20, col,
    pp: 0, violations: 3, complianceRate: 0.5, particles: [],
  };
}

describe('galaxyFolderDraw nebula discs', () => {
  let discs;

  beforeEach(() => {
    discs = [];
    vi.clearAllMocks();
  });

  it('drawNebula paints one background disc plus four orbiting blobs', () => {
    const ctx = makeRecordingCtx(discs);
    drawNebula(ctx, { complianceRate: 0.5 }, {}, { W: 800, H: 600, t: 12 });
    expect(discs).toHaveLength(5);
    expect(discs).toMatchSnapshot('scene-nebula-discs');
  });

  it('a folder star paints its cluster nebula plus three blobs, zoomed in', () => {
    const ctx = makeRecordingCtx(discs);
    const scene = { rootStars: [makeFolderStar()], lines: [], bg: [] };
    drawStars(ctx, scene, {
      t: 7, cam: { x: 0, y: 0, z: 4 }, w2s: (x, y) => ({ x, y }), showLabels: false,
      mouseRef: { current: { x: -1, y: -1 } }, flyRef: { current: null },
      focusedFolderRef: { current: null }, animRef: { current: null },
      tc: { text: { r: 1, g: 1, b: 1 }, textMuted: { r: 1, g: 1, b: 1 } },
    });
    expect(discs).toMatchSnapshot('folder-nebula-discs-zoomed');
  });

  it('a folder star paints the same blob ring when zoomed out', () => {
    const ctx = makeRecordingCtx(discs);
    const scene = { rootStars: [makeFolderStar()], lines: [], bg: [] };
    drawStars(ctx, scene, {
      t: 3, cam: { x: 0, y: 0, z: 1 }, w2s: (x, y) => ({ x, y }), showLabels: false,
      mouseRef: { current: { x: -1, y: -1 } }, flyRef: { current: null },
      focusedFolderRef: { current: null }, animRef: { current: null },
      tc: { text: { r: 1, g: 1, b: 1 }, textMuted: { r: 1, g: 1, b: 1 } },
    });
    expect(discs).toMatchSnapshot('folder-nebula-discs-zoomed-out');
  });
});
