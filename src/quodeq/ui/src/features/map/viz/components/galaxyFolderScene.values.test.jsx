/**
 * Value-level characterization for galaxyFolderScene. The sibling
 * galaxyFolderScene.test.jsx locks the output SHAPE; this one locks the
 * numbers: star radii, spread factors, folder/file orbit distances, the two
 * particle builders' ranges, the repulsion gap and pass counts, the
 * fit-to-target scaling and the background-star ranges.
 *
 * scoreRGB/sevRGB reach getThemeColors, which parses CSS through a real 2D
 * context (unavailable under JSDOM), so only those two are mocked; the
 * seeded RNG stays real. Math.random (background stars) is stubbed so the
 * decorative field snapshots stably.
 *
 * Captured from the pre-naming code — keep the snapshots unchanged.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../core/galaxyCore.js', async (importOriginal) => {
  const actual = await importOriginal();
  const col = { r: 100, g: 150, b: 200 };
  return { ...actual, scoreRGB: () => col, sevRGB: () => col };
});

import { buildFolderScene, countDescendants, layoutChildren } from './galaxyFolderScene.js';

const round = (n) => (typeof n === 'number' ? Number(n.toFixed(6)) : n);

function file(name, violations, severity) {
  return {
    name, path: name, isFile: true, violations, compliance: 1,
    complianceRate: 0.5, severity: severity || {}, children: [],
  };
}

function folder(name, children, extra) {
  return {
    name, path: name, isFile: false, violations: 2, compliance: 3,
    complianceRate: 0.6, severity: { critical: 1, major: 2, minor: 4 },
    children, ...extra,
  };
}

function makeNode() {
  return folder('root', [
    folder('src', [file('src/a.js', 1, { critical: 1 }), file('src/b.js', 0)]),
    folder('lib', [file('lib/c.js', 5, { critical: 2, major: 3, minor: 12 }), file('lib/d.js', 0)]),
    file('index.js', 3, { major: 1, minor: 2 }),
    file('README.md', 0),
  ]);
}

describe('galaxyFolderScene value characterization', () => {
  let randomSpy;
  beforeEach(() => {
    let i = 0;
    randomSpy = vi.spyOn(Math, 'random').mockImplementation(() => ((i++ * 7) % 11) / 11);
  });
  afterEach(() => { randomSpy.mockRestore(); });

  it('places every root star at the recorded radius and offset', () => {
    const scene = buildFolderScene(makeNode(), 800, 600);
    expect(scene.rootStars.map((s) => ({
      name: s.name, isFolder: s.isFolder,
      radius: round(s.radius), ox: round(s.ox), oy: round(s.oy), pp: round(s.pp),
    }))).toMatchSnapshot('root-star-geometry');
    expect(scene.lines).toMatchSnapshot('mst-lines');
    expect(round(scene._maxExtent)).toMatchSnapshot('max-extent');
  });

  it('builds folder-nebula alert particles from the recorded ranges', () => {
    const scene = buildFolderScene(makeNode(), 800, 600);
    const src = scene.rootStars.find((s) => s.name === 'src');
    expect(src.particles.map((p) => ({
      sev: p.sev, or: round(p.or), os: round(p.os), op: round(p.op),
      sz: round(p.sz), ec: round(p.ec), tp: round(p.tp),
    }))).toMatchSnapshot('folder-alert-particles');
  });

  it('builds per-file violation particles from the recorded ranges', () => {
    const scene = buildFolderScene(makeNode(), 800, 600);
    const idx = scene.rootStars.find((s) => s.name === 'index.js');
    expect(idx.particles.map((p) => ({
      sev: p.sev, or: round(p.or), os: round(p.os), op: round(p.op),
      sz: round(p.sz), ec: round(p.ec), tp: round(p.tp),
    }))).toMatchSnapshot('file-violation-particles');
  });

  it('caps folder alert blips per severity and file particles per severity', () => {
    const scene = buildFolderScene(makeNode(), 800, 600);
    const lib = scene.rootStars.find((s) => s.name === 'lib');
    // Folder blips: one per violation, capped at three per severity, so
    // critical 1 + major 2 + minor 4-capped-to-3 is six.
    expect(lib.particles).toHaveLength(6);
    expect(lib.particles.filter((p) => p.sev === 'minor')).toHaveLength(3);
    // A single-child folder chain ending in a file is unwrapped to that file.
    expect(scene.rootStars.map((s) => s.name)).not.toContain('lib/c.js');
    const many = buildFolderScene(
      folder('r', [file('big.js', 40, { critical: 40, major: 40, minor: 40 })]), 800, 600,
    );
    expect(many.rootStars[0].particles).toHaveLength(30);
  });

  it('scales a too-wide layout down to the target radius fraction', () => {
    const wide = folder('r', Array.from({ length: 12 }, (_, i) => folder('d' + i, [file('d' + i + '/x.js', 1)])));
    const scene = buildFolderScene(wide, 400, 300);
    expect(round(scene._maxExtent)).toBeCloseTo(Math.min(400, 300) * 0.42, 6);
  });

  it('keeps the background starfield count, size and speed ranges', () => {
    const scene = buildFolderScene(makeNode(), 800, 600);
    expect(scene.bg).toHaveLength(120);
    expect(scene.bg.slice(0, 4).map((s) => ({
      x: round(s.x), y: round(s.y), sz: round(s.sz), tw: round(s.tw), sp: round(s.sp),
    }))).toMatchSnapshot('background-star-values');
    expect(Math.max(...scene.bg.map((s) => s.sz))).toBeLessThanOrEqual(1.2);
    expect(Math.min(...scene.bg.map((s) => s.sp))).toBeGreaterThanOrEqual(0.3);
    expect(Math.max(...scene.bg.map((s) => s.sp))).toBeLessThanOrEqual(1);
  });

  it('layoutChildren and countDescendants stay deterministic per node', () => {
    const node = makeNode();
    expect(countDescendants(node)).toBe(8);
    expect(layoutChildren(node).map((p) => ({
      name: p.child.name, isFolder: p.isFolder, angle: round(p.angle), dist: round(p.dist),
    }))).toMatchSnapshot('layout-children');
  });

  it('applies more repulsion passes to small scenes than to large ones', () => {
    const big = folder('r', Array.from({ length: 60 }, (_, i) => file('f' + i + '.js', 1)));
    const small = folder('r', Array.from({ length: 6 }, (_, i) => file('f' + i + '.js', 1)));
    const a = buildFolderScene(big, 800, 600);
    const b = buildFolderScene(small, 800, 600);
    expect(a.rootStars.map((s) => round(s.ox))).toMatchSnapshot('large-scene-ox');
    expect(b.rootStars.map((s) => round(s.ox))).toMatchSnapshot('small-scene-ox');
  });

  it('gives a flagged file with no severity counts no particles', () => {
    const bare = { ...file('x.js', 2), severity: undefined };
    const scene = buildFolderScene(folder('r', [bare, file('y.js', 0)]), 800, 600);
    expect(scene.rootStars.find((s) => s.name === 'x.js').particles).toEqual([]);
  });
});
