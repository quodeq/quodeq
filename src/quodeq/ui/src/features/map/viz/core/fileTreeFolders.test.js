import test from 'node:test';
import assert from 'node:assert/strict';
import { isDrillableFolder } from './fileTree.js';

test('isDrillableFolder is true only for a folder with children', () => {
  assert.equal(isDrillableFolder({ isFile: false, children: [{}] }), true);
});

test('isDrillableFolder is false for files, empty folders and folders without a child list', () => {
  const nodes = [{ isFile: true, children: [{}] }, { isFile: false, children: [] }, { isFile: false }];
  assert.deepEqual(nodes.map(isDrillableFolder), [false, false, false]);
});
