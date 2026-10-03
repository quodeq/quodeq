import { hierarchy, pack } from 'd3-hierarchy';
import { nodeSize } from './mapColors.js';

// Layout units for the circle pack; the SVG viewBox scales them to the screen.
export const PACK_BASE_SIZE = 600;
// Gap d3-pack leaves between a top-level circle and the root, in layout units.
export const PACK_PADDING = 8;
// Trees at or above this many nodes lay out in the worker instead of the
// render thread.
export const PACK_WORKER_NODE_THRESHOLD = 2000;
const XYR_STRIDE = 3;

/** The d3 hierarchy for a file-tree node: leaf values from `viewMode`,
 * children sorted largest first. Cheap next to the pack itself. */
export function buildPackRoot(node, viewMode) {
  return hierarchy(node, (d) => d.children || [])
    .sum((d) => (d.children?.length ? 0 : Math.max(1, nodeSize(d, viewMode))))
    .sort((a, b) => (b.value || 0) - (a.value || 0));
}

/** Padding around a folder's children, shrinking with depth. d3 scales the
 * padding by the unpadded root radius, so on deep source trees a flat value
 * dwarfs the file circles and leaves every deep folder mostly empty. */
export function packPadding(node) {
  return PACK_PADDING / (1 + node.depth);
}

/** Run the pack on a hierarchy in place. */
export function packInPlace(root) {
  pack().size([PACK_BASE_SIZE, PACK_BASE_SIZE]).padding(packPadding)(root);
  return root;
}

export function layoutCircles(root) {
  return root.descendants().filter((c) => c.r > 0);
}

/** A structured-clone friendly copy of a hierarchy: values and child order
 * only, no file data. Children keep the sorted order so preorder indices
 * line up with `root.descendants()` on the other side. */
export function slimTree(root) {
  const slim = { v: root.value };
  if (root.children) slim.c = root.children.map(slimTree);
  return slim;
}

/** Pack a slim tree and return `[x, y, r]` per node in preorder. */
export function packSlim(slim) {
  const root = hierarchy(slim, (d) => d.c).each((n) => { n.value = n.data.v; });
  packInPlace(root);
  const nodes = root.descendants();
  const xyr = new Float64Array(nodes.length * XYR_STRIDE);
  nodes.forEach((n, i) => {
    xyr[i * XYR_STRIDE] = n.x;
    xyr[i * XYR_STRIDE + 1] = n.y;
    xyr[i * XYR_STRIDE + 2] = n.r;
  });
  return xyr;
}

/** Write worker positions back onto the hierarchy the slim tree came from. */
export function applyPositions(root, xyr) {
  root.descendants().forEach((n, i) => {
    n.x = xyr[i * XYR_STRIDE];
    n.y = xyr[i * XYR_STRIDE + 1];
    n.r = xyr[i * XYR_STRIDE + 2];
  });
  return root;
}

/** The worker's whole job, kept pure so tests run it without a Worker. */
export function handlePackMessage({ id, slim }) {
  return { id, xyr: packSlim(slim) };
}
