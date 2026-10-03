import { describe, it, expect } from 'vitest';
import { buildPackRoot, packInPlace, slimTree, applyPositions, handlePackMessage, packPadding, PACK_PADDING } from './packLayout.js';
import { MAP_VIEW_MODE } from '../../mapVocab.js';

const FIXTURE = {
  name: '/', path: '', isFile: false, violations: 6, compliance: 2, severity: {},
  children: [
    { name: 'a', path: 'a', isFile: false, violations: 4, compliance: 1, severity: {}, children: [
      { name: 'a1.py', path: 'a/a1.py', isFile: true, violations: 3, compliance: 0, severity: {} },
      { name: 'a2.py', path: 'a/a2.py', isFile: true, violations: 1, compliance: 1, severity: {} },
    ] },
    { name: 'b.py', path: 'b.py', isFile: true, violations: 2, compliance: 1, severity: {} },
  ],
};

describe('pack layout: worker path matches the render-thread path', () => {
  it.each(Object.values(MAP_VIEW_MODE))('in %s mode', (mode) => {
    const sync = packInPlace(buildPackRoot(FIXTURE, mode));
    const viaWorker = buildPackRoot(FIXTURE, mode);
    const { id, xyr } = handlePackMessage({ id: 7, slim: slimTree(viaWorker) });
    applyPositions(viaWorker, xyr);

    expect(id).toBe(7);
    const pos = (root) => root.descendants().map((n) => [n.data.path, n.x, n.y, n.r]);
    expect(pos(viaWorker)).toEqual(pos(sync));
  });

  it('slim trees carry no file data', () => {
    const slim = slimTree(buildPackRoot(FIXTURE, MAP_VIEW_MODE.HEALTH));
    expect(JSON.stringify(slim)).not.toContain('a1.py');
    expect(Object.keys(slim).sort()).toEqual(['c', 'v']);
  });
});

describe('pack padding shrinks with depth', () => {
  const file = (path) => ({ name: path, path, isFile: true, violations: 1, compliance: 0, severity: {} });
  const folder = (path, children) => ({ name: path, path, isFile: false, violations: 0, compliance: 0, severity: {}, children });
  // A deep, sparse tree like a real source repo: each nesting level wastes
  // area, which inflates d3's padding relative to the tiny file circles.
  function deepTree(prefix, depth) {
    if (depth === 0) return [file(`${prefix}/a.py`), file(`${prefix}/b.py`)];
    return [0, 1].map((i) => folder(`${prefix}/d${i}`, deepTree(`${prefix}/d${i}`, depth - 1)));
  }
  const DEEP_LEVELS = 6;
  const TREE = folder('', [...deepTree('', DEEP_LEVELS), folder('x', [folder('x/y', [file('x/y/one.py')])])]);

  it('a deep single-file folder is mostly filled by its file', () => {
    const root = packInPlace(buildPackRoot(TREE, MAP_VIEW_MODE.VIOLATIONS));
    const byPath = new Map(root.descendants().map((n) => [n.data.path, n]));
    const fill = byPath.get('x/y/one.py').r / byPath.get('x/y').r;
    // Flat padding leaves this at ~0.23.
    expect(fill).toBeGreaterThan(0.4);
  });

  it('padding at the top level stays at the base value', () => {
    expect(packPadding({ depth: 0 })).toBe(PACK_PADDING);
    expect(packPadding({ depth: 3 })).toBeLessThan(PACK_PADDING / 2);
  });
});
