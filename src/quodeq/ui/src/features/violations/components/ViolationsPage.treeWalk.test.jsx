import { describe, it, expect } from 'vitest';
import { findParentPath, buildBreadcrumbPath } from './ViolationsPage.jsx';

function node(name, path, children = []) {
  return { name, path, isFile: children.length === 0, children };
}

function sampleTree() {
  return node('/', '', [
    node('src', 'src', [
      node('auth', 'src/auth', [node('login.py', 'src/auth/login.py')]),
      node('api', 'src/api', [node('routes.py', 'src/api/routes.py')]),
    ]),
    node('README.md', 'README.md'),
  ]);
}

// buildFileTree's ensurePath nests one node per path segment with no cap, so
// a pathological payload can hand these walkers an arbitrarily deep tree.
function chain(depth) {
  let current = node(`n${depth - 1}`, `p${depth - 1}`);
  const leaf = current;
  for (let i = depth - 2; i >= 0; i--) current = node(`n${i}`, `p${i}`, [current]);
  return { root: node('/', '', [current]), leaf };
}

describe('findParentPath', () => {
  it('returns the parent path of the current node, or the root for top-level and unknown paths', () => {
    const root = sampleTree();
    expect(findParentPath(root, 'src/auth/login.py')).toBe('src/auth');
    expect(findParentPath(root, 'src/api')).toBe('src');
    expect(findParentPath(root, 'src')).toBe('');
    expect(findParentPath(root, 'missing')).toBe('');
  });

  it('does not overflow the stack on a pathologically deep tree', () => {
    const { root, leaf } = chain(100_000);
    expect(() => findParentPath(root, leaf.path)).not.toThrow();
    expect(findParentPath(root, leaf.path)).toBe('');
    // Nodes within the depth cap still resolve.
    expect(findParentPath(root, 'p10')).toBe('p9');
  });
});

describe('buildBreadcrumbPath', () => {
  it('lists the ancestors down to the current node, omitting the root', () => {
    const root = sampleTree();
    expect(buildBreadcrumbPath(root, 'src/auth/login.py')).toEqual([
      { name: 'src', path: 'src' },
      { name: 'auth', path: 'src/auth' },
      { name: 'login.py', path: 'src/auth/login.py' },
    ]);
    expect(buildBreadcrumbPath(root, '')).toEqual([]);
    expect(buildBreadcrumbPath(root, 'missing')).toEqual([]);
  });

  it('does not overflow the stack on a pathologically deep tree', () => {
    const { root, leaf } = chain(100_000);
    expect(() => buildBreadcrumbPath(root, leaf.path)).not.toThrow();
    expect(buildBreadcrumbPath(root, leaf.path)).toEqual([]);
    expect(buildBreadcrumbPath(root, 'p3').map((s) => s.path)).toEqual(['p0', 'p1', 'p2', 'p3']);
  });
});
