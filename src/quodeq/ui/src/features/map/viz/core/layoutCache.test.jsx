import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./packWorkerClient.js', () => ({ requestPackLayout: vi.fn() }));
vi.mock('./fileTree.js', async (importOriginal) => {
  const mod = await importOriginal();
  return { ...mod, buildFileTree: vi.fn(mod.buildFileTree) };
});

import { buildFileTree } from './fileTree.js';
import { requestPackLayout } from './packWorkerClient.js';
import { cachedFileTree, resolvePackLayout } from './layoutCache.js';
import { buildPackRoot, packInPlace, slimTree, packSlim, PACK_WORKER_NODE_THRESHOLD } from './packLayout.js';
import { MAP_VIEW_MODE } from '../../mapVocab.js';

const dimA = { dimension: 'a', violations: [{ file: 'x/a.py' }], compliance: [] };
const dimB = { dimension: 'b', violations: [{ file: 'y/b.py' }], compliance: [] };

function wideTree(files) {
  const children = Array.from({ length: files }, (_, i) => ({
    name: `f${i}.py`, path: `src/f${i}.py`, isFile: true, violations: i + 1, compliance: 0, severity: {},
  }));
  return { name: '/', path: '', isFile: false, violations: 0, compliance: 0, severity: {}, children };
}

beforeEach(() => {
  buildFileTree.mockClear();
  requestPackLayout.mockReset();
});

describe('cachedFileTree', () => {
  it('reuses the tree for the same dimension objects in a fresh array', () => {
    const first = cachedFileTree([dimA, dimB]);
    const second = cachedFileTree([dimA, dimB]);
    expect(second).toBe(first);
    expect(buildFileTree).toHaveBeenCalledTimes(1);
  });

  it('misses on a different selection or order', () => {
    cachedFileTree([dimA, dimB]);
    cachedFileTree([dimB, dimA]);
    cachedFileTree([dimA]);
    expect(buildFileTree).toHaveBeenCalledTimes(2);
  });
});

describe('resolvePackLayout', () => {
  it('lays out small trees on the render thread and caches per node and mode', () => {
    const node = wideTree(3);
    const a = resolvePackLayout(node, MAP_VIEW_MODE.HEALTH);
    expect(a.pending).toBe(false);
    expect(a.circles.length).toBe(4);
    expect(resolvePackLayout(node, MAP_VIEW_MODE.HEALTH)).toBe(a);
    expect(resolvePackLayout(node, MAP_VIEW_MODE.VIOLATIONS)).not.toBe(a);
    expect(requestPackLayout).not.toHaveBeenCalled();
  });

  it('hands large trees to the worker and settles with the same circles as the render thread', async () => {
    const node = wideTree(PACK_WORKER_NODE_THRESHOLD);
    requestPackLayout.mockImplementation((slim) => Promise.resolve(packSlim(slim)));
    const first = resolvePackLayout(node, MAP_VIEW_MODE.HEALTH);
    expect(first.pending).toBe(true);
    expect(first.circles).toEqual([]);
    const done = await first.promise;
    expect(done.pending).toBe(false);
    expect(resolvePackLayout(node, MAP_VIEW_MODE.HEALTH)).toBe(done);

    const sync = packInPlace(buildPackRoot(node, MAP_VIEW_MODE.HEALTH)).descendants();
    done.root.descendants().forEach((n, i) => {
      expect([n.x, n.y, n.r]).toEqual([sync[i].x, sync[i].y, sync[i].r]);
    });
    expect(slimTree(done.root).c.length).toBe(PACK_WORKER_NODE_THRESHOLD);
  });

  it('falls back to the render thread when the worker fails', async () => {
    requestPackLayout.mockReturnValue(Promise.reject(new Error('boom')));
    const first = resolvePackLayout(wideTree(PACK_WORKER_NODE_THRESHOLD), MAP_VIEW_MODE.HEALTH);
    const done = await first.promise;
    expect(done.circles.length).toBe(PACK_WORKER_NODE_THRESHOLD + 1);
  });

  it('falls back to the render thread when no worker is available', () => {
    requestPackLayout.mockReturnValue(null);
    const layout = resolvePackLayout(wideTree(PACK_WORKER_NODE_THRESHOLD), MAP_VIEW_MODE.HEALTH);
    expect(layout.pending).toBe(false);
    expect(layout.circles.length).toBe(PACK_WORKER_NODE_THRESHOLD + 1);
  });
});
