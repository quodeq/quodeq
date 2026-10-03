import { buildFileTree } from './fileTree.js';
import {
  buildPackRoot, packInPlace, layoutCircles, slimTree, applyPositions, PACK_WORKER_NODE_THRESHOLD,
} from './packLayout.js';
import { requestPackLayout } from './packWorkerClient.js';

// Module-level caches so a second Map visit with the same scores payload
// neither rebuilds the file tree nor re-runs the pack. Keys are object
// identities (the dimension objects and tree nodes react-query hands back
// unchanged), so a new payload naturally misses.

class TrieNode {
  constructor() {
    this.children = new WeakMap();
    this.value = undefined;
  }
}

const treeCache = new TrieNode();

/** `buildFileTree(dimensions)`, memoised on the identity of each dimension
 * object in order. The array itself may be freshly filtered every render. */
export function cachedFileTree(dimensions) {
  let node = treeCache;
  for (const dim of dimensions) {
    let next = node.children.get(dim);
    if (!next) {
      next = new TrieNode();
      node.children.set(dim, next);
    }
    node = next;
  }
  if (node.value === undefined) node.value = buildFileTree(dimensions);
  return node.value;
}

const layoutCache = new WeakMap();

function getLayout(node, viewMode) {
  return layoutCache.get(node)?.get(viewMode);
}

function setLayout(node, viewMode, layout) {
  let byMode = layoutCache.get(node);
  if (!byMode) {
    byMode = new Map();
    layoutCache.set(node, byMode);
  }
  byMode.set(viewMode, layout);
  return layout;
}

function finishLayout(node, viewMode, root) {
  return setLayout(node, viewMode, { root, circles: layoutCircles(root), pending: false });
}

function layoutInWorker(node, viewMode, root) {
  const reply = requestPackLayout(slimTree(root));
  if (!reply) return finishLayout(node, viewMode, packInPlace(root));
  const promise = reply
    .then((xyr) => finishLayout(node, viewMode, applyPositions(root, xyr)))
    .catch(() => finishLayout(node, viewMode, packInPlace(root)));
  // No root until the positions land: the view derives its focus transform
  // from the root's radius and memoises on the root's identity, so handing
  // out the unpositioned root now would freeze NaN in that transform.
  return { root: null, circles: [], pending: true, promise };
}

/** The pack layout for `node`: the cached result when there is one,
 * otherwise computed now for small trees, or handed to the worker for large
 * ones (`pending: true`, with `promise` resolving to the finished layout). */
export function resolvePackLayout(node, viewMode) {
  if (!node) return { root: null, circles: [], pending: false };
  const hit = getLayout(node, viewMode);
  if (hit) return hit;
  const root = buildPackRoot(node, viewMode);
  if (!root.value) return setLayout(node, viewMode, { root, circles: [], pending: false });
  if (root.descendants().length < PACK_WORKER_NODE_THRESHOLD) return finishLayout(node, viewMode, packInPlace(root));
  return setLayout(node, viewMode, layoutInWorker(node, viewMode, root));
}
