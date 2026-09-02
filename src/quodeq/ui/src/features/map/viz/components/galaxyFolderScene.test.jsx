import { describe, it, expect, vi } from 'vitest';
import { buildFolderScene, buildNavPath, buildLevelInfo } from './galaxyFolderScene.js';

// Characterization test written BEFORE buildFolderScene is split into phase
// helpers (placeRootStars/recenterStars/applyRepulsion/normalizeToFit/
// buildMST/buildBackgroundStars). Locks the OUTPUT SHAPE (not exact magic
// numbers — the layout involves a seeded RNG for star placement, so exact
// coordinates aren't a stable contract) and the determinism guarantee: the
// same input node always produces the same star layout.
//
// scoreRGB/sevRGB reach into galaxyCore's getThemeColors, which parses CSS
// colors through a real canvas 2D context — unavailable under jsdom (see
// vitest.setup.js, which stubs getContext to return null). Mock just those
// two color lookups; seedHash/seededRng (the star-placement RNG) stay real
// so the determinism assertions below exercise real code.
vi.mock('../core/galaxyCore.js', async (importOriginal) => {
  const actual = await importOriginal();
  const col = { r: 100, g: 150, b: 200 };
  return { ...actual, scoreRGB: () => col, sevRGB: () => col };
});

function makeNode() {
  return {
    name: 'root',
    path: '',
    isFile: false,
    violations: 3,
    compliance: 2,
    complianceRate: 0.6,
    severity: { critical: 1, major: 0, minor: 2 },
    children: [
      {
        name: 'src',
        path: 'src',
        isFile: false,
        violations: 3,
        compliance: 2,
        complianceRate: 0.5,
        severity: { critical: 1, major: 1, minor: 0 },
        children: [{ name: 'a.js', path: 'src/a.js', isFile: true, violations: 1, compliance: 0, complianceRate: 0, severity: {}, children: [] }],
      },
      {
        name: 'index.js',
        path: 'index.js',
        isFile: true,
        violations: 2,
        compliance: 1,
        complianceRate: 0.5,
        severity: { critical: 0, major: 1, minor: 1 },
        children: [],
      },
    ],
  };
}

describe('buildFolderScene output shape', () => {
  it('returns the expected top-level shape', () => {
    const scene = buildFolderScene(makeNode(), 800, 600);
    expect(Array.isArray(scene.rootStars)).toBe(true);
    expect(scene.rootStars.length).toBe(2);
    expect(Array.isArray(scene.lines)).toBe(true);
    expect(Array.isArray(scene.bg)).toBe(true);
    expect(scene.bg.length).toBe(120);
    expect(typeof scene._maxExtent).toBe('number');
  });

  it('rootStars carry the expected per-star fields', () => {
    const scene = buildFolderScene(makeNode(), 800, 600);
    for (const s of scene.rootStars) {
      expect(typeof s.name).toBe('string');
      expect(typeof s.isFolder).toBe('boolean');
      expect(typeof s.radius).toBe('number');
      expect(typeof s.ox).toBe('number');
      expect(typeof s.oy).toBe('number');
      expect(typeof s.x).toBe('number');
      expect(typeof s.y).toBe('number');
      expect(Array.isArray(s.particles)).toBe(true);
      expect(s._node).toBeTruthy();
    }
  });

  it('MST connects every star with rootStars.length - 1 lines', () => {
    const scene = buildFolderScene(makeNode(), 800, 600);
    expect(scene.lines.length).toBe(scene.rootStars.length - 1);
    for (const l of scene.lines) {
      expect(typeof l.a).toBe('number');
      expect(typeof l.b).toBe('number');
    }
  });

  it('star placement is deterministic for the same node', () => {
    const node = makeNode();
    const a = buildFolderScene(node, 800, 600);
    const b = buildFolderScene(node, 800, 600);
    expect(a.rootStars.map((s) => ({ ox: s.ox, oy: s.oy, radius: s.radius }))).toEqual(
      b.rootStars.map((s) => ({ ox: s.ox, oy: s.oy, radius: s.radius })),
    );
  });
});

describe('buildNavPath / buildLevelInfo', () => {
  it('buildNavPath walks from root to the target path', () => {
    const node = makeNode();
    const path = buildNavPath(node, 'src');
    expect(path.length).toBe(2);
    expect(path[path.length - 1].path).toBe('src');
  });

  it('buildLevelInfo summarizes the current node when nothing is zoomed', () => {
    const node = makeNode();
    const scene = buildFolderScene(node, 800, 600);
    const info = buildLevelInfo({
      scene,
      currentNode: node,
      zoomedFileRef: { current: null },
      navRef: { current: { path: [node] } },
      projectName: 'Demo',
      onFileClick: () => {},
    });
    expect(info.title).toBe('Demo');
    expect(Array.isArray(info.lines)).toBe(true);
  });
});
