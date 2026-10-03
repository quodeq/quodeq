import test from 'node:test';
import assert from 'node:assert/strict';
import { parentChain } from './i18n_rules.mjs';

function chain(...types) {
  let node = null;
  for (const type of types.reverse()) node = { type, parent: node };
  return node;
}

test('parentChain yields each parent with the child it was reached from and the step index', () => {
  const leaf = chain('Literal', 'A', 'B');
  const steps = [...parentChain(leaf, 5)].map(([parent, child, depth]) => [parent.type, child.type, depth]);
  assert.deepEqual(steps, [['A', 'Literal', 0], ['B', 'A', 1]]);
});

test('parentChain stops after maxDepth steps', () => {
  const leaf = chain('Literal', 'A', 'B', 'C');
  assert.deepEqual([...parentChain(leaf, 2)].map(([parent]) => parent.type), ['A', 'B']);
});

test('parentChain yields nothing for a root node', () => {
  assert.deepEqual([...parentChain({ type: 'Program', parent: null }, 4)], []);
});
