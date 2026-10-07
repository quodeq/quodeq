import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createProject } from './project.js';

test('project info carries the last finished run\'s dimensions, [] when absent', () => {
  assert.deepEqual(createProject({ id: 'p', latestRunDimensions: ['security'] }).latestRunDimensions, ['security']);
  assert.deepEqual(createProject({ id: 'p' }).latestRunDimensions, []);
});
