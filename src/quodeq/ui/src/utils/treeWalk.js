// buildFileTree nests one node per path segment with no cap, so a
// pathological payload can hand a walker an arbitrarily deep tree. Past this
// depth the subtree is treated as absent rather than blowing the stack.
const DEFAULT_MAX_DEPTH = 64;

/**
 * Depth-first search over a `{ path, name, children }` tree.
 *
 * Calls `visit(node, ancestors)` on each node, root first; the first node for
 * which `visit` returns a truthy value is returned. `ancestors` lists the
 * node's ancestors root-first and is REUSED between visits, so a visitor that
 * keeps it must copy it.
 *
 * @param {object|null} root Tree root; a missing root yields null.
 * @param {(node: object, ancestors: object[]) => boolean} visit Truthy to stop.
 * @param {{maxDepth?: number}} [options] Recursion cap (root is depth 0).
 * @returns {object|null} The accepted node, or null if none was accepted.
 */
export function walkTree(root, visit, { maxDepth = DEFAULT_MAX_DEPTH } = {}) {
  const ancestors = [];
  function step(node, depth) {
    if (depth > maxDepth) return null;
    if (visit(node, ancestors)) return node;
    ancestors.push(node);
    let found = null;
    for (const child of node.children || []) {
      found = step(child, depth + 1);
      if (found) break;
    }
    ancestors.pop();
    return found;
  }
  return root ? step(root, 0) : null;
}
