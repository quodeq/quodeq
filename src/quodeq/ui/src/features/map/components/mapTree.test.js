import { test } from 'node:test';
import assert from 'node:assert/strict';
import { findSubtree, buildBreadcrumbPath } from './mapTree.js';

function node(path, name, children = []) {
  return { path, name, children };
}

const leaf = node('src/app/main.py', 'main.py');
const app = node('src/app', 'app', [leaf]);
const libNode = node('src/lib', 'lib');
const src = node('src', 'src', [app, libNode]);
const root = node('', '(root)', [src]);

test('findSubtree returns the root for an empty path', () => {
  assert.equal(findSubtree(root, ''), root);
  assert.equal(findSubtree(root, null), root);
});

test('findSubtree locates a nested node by exact path', () => {
  assert.equal(findSubtree(root, 'src/app'), app);
  assert.equal(findSubtree(root, 'src/app/main.py'), leaf);
});

test('findSubtree only descends into prefix-matching children', () => {
  // 'src/application' shares the string prefix 'src/app' but is NOT under
  // src/app the directory — the '/'-boundary check must reject it and the
  // lookup falls back to root.
  assert.equal(findSubtree(root, 'src/application'), root);
});

test('findSubtree falls back to the root for an unknown path', () => {
  assert.equal(findSubtree(root, 'does/not/exist'), root);
});

test('buildBreadcrumbPath returns the ancestor chain excluding the root', () => {
  assert.deepEqual(buildBreadcrumbPath(root, 'src/app/main.py'), [
    { name: 'src', path: 'src' },
    { name: 'app', path: 'src/app' },
    { name: 'main.py', path: 'src/app/main.py' },
  ]);
});

test('buildBreadcrumbPath is empty for no path and stops at the deepest resolvable hop', () => {
  assert.deepEqual(buildBreadcrumbPath(root, ''), []);
  // Unknown leaf under a known folder: crumbs cover the resolvable prefix.
  assert.deepEqual(buildBreadcrumbPath(root, 'src/lib/missing.py'), [
    { name: 'src', path: 'src' },
    { name: 'lib', path: 'src/lib' },
  ]);
});
