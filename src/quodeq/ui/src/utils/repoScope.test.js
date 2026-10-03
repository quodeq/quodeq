import { test } from 'node:test';
import assert from 'node:assert/strict';
import { toRepoRelativeScope } from './repoScope.js';

test('strips only a real path prefix', () => {
  assert.equal(toRepoRelativeScope('/repo/src/a', '/repo'), 'src/a');
  assert.equal(toRepoRelativeScope('/repo', '/repo'), '');
  assert.equal(toRepoRelativeScope('/repo2/x', '/repo'), '/repo2/x');
});

test('no root returns the path unchanged', () => {
  assert.equal(toRepoRelativeScope('/repo/src/a', null), '/repo/src/a');
  assert.equal(toRepoRelativeScope('/repo/src/a', ''), '/repo/src/a');
});

test('a root with a trailing slash still anchors correctly', () => {
  assert.equal(toRepoRelativeScope('/repo/src/a', '/repo/'), 'src/a');
});
