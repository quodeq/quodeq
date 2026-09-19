import test from 'node:test';
import assert from 'node:assert/strict';
import { walkTree } from './treeWalk.js';

function node(name, path, children = []) {
  return { name, path, children };
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

test('walkTree returns the first node the visitor accepts, found at depth 2', () => {
  const root = sampleTree();
  const found = walkTree(root, (n) => n.path === 'src/auth');
  assert.equal(found, root.children[0].children[0]);
});

test('walkTree returns null when no node is accepted', () => {
  assert.equal(walkTree(sampleTree(), (n) => n.path === 'missing'), null);
});

test('walkTree does not descend past maxDepth', () => {
  const root = sampleTree();
  // 'src/auth' sits at depth 2, so a cap of 1 must hide it while a cap of 2
  // still reaches it.
  assert.equal(walkTree(root, (n) => n.path === 'src/auth', { maxDepth: 1 }), null);
  assert.equal(walkTree(root, (n) => n.path === 'src/auth', { maxDepth: 2 }), root.children[0].children[0]);
});

test('walkTree passes the visitor the ancestors of the current node, root first', () => {
  const root = sampleTree();
  let ancestors = null;
  walkTree(root, (n, path) => {
    if (n.path !== 'src/auth/login.py') return false;
    ancestors = path.map((a) => a.path);
    return true;
  });
  assert.deepEqual(ancestors, ['', 'src', 'src/auth']);
});

test('walkTree treats a node with no children array as a leaf', () => {
  assert.equal(walkTree({ path: 'x' }, (n) => n.path === 'y'), null);
});

test('walkTree returns null for a missing root', () => {
  assert.equal(walkTree(null, () => true), null);
});
