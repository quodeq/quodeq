/**
 * Pure tree navigation for the map page: no DOM, no fetch, no storage.
 * Extracted from useMapPageState so the filtering/breadcrumb logic is
 * unit-testable without mounting the hook.
 */
const MAX_TREE_DEPTH = 64;

/** Locate the subtree whose node.path equals `path`; falls back to root. */
export function findSubtree(root, path) {
  if (!path) return root;
  function walk(node, depth = 0) {
    if (depth > MAX_TREE_DEPTH) return null;
    if (node.path === path) return node;
    for (const child of node.children) {
      if (path === child.path || path.startsWith(child.path + '/')) {
        const found = walk(child, depth + 1);
        if (found) return found;
      }
    }
    return null;
  }
  return walk(root) || root;
}

/** Ancestor chain (name/path pairs) from root down to `path`, excluding root. */
export function buildBreadcrumbPath(root, path) {
  if (!path) return [];
  const crumbs = [];
  let node = root;
  while (node && node.path !== path) {
    const child = node.children.find((c) => path === c.path || path.startsWith(c.path + '/'));
    if (!child) break;
    crumbs.push({ name: child.name, path: child.path });
    node = child;
  }
  return crumbs;
}
