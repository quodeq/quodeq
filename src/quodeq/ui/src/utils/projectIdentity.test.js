import test from 'node:test';
import assert from 'node:assert/strict';
import { findProject, projectId, projectIdOrSelf } from './projectIdentity.js';

test('projectId prefers the id and falls back to the name', () => {
  assert.equal(projectId({ id: 'abc', name: 'repo' }), 'abc');
  assert.equal(projectId({ id: null, name: 'repo' }), 'repo');
  assert.equal(projectId({ id: '', name: '' }), '');
  assert.equal(projectId('bare-name'), undefined);
});

test('projectIdOrSelf also accepts a bare project name', () => {
  assert.equal(projectIdOrSelf({ id: 'abc', name: 'repo' }), 'abc');
  assert.equal(projectIdOrSelf({ id: null, name: 'repo' }), 'repo');
  assert.equal(projectIdOrSelf('bare-name'), 'bare-name');
});

test('findProject returns the project whose key matches', () => {
  const projects = [{ id: 'a', name: 'one' }, { id: null, name: 'two' }];
  assert.deepEqual([findProject(projects, 'a'), findProject(projects, 'two')], projects);
});

test('findProject returns null for no match or no list', () => {
  assert.deepEqual([findProject([{ id: 'a' }], 'zzz'), findProject(undefined, 'a'), findProject(null, 'a')], [null, null, null]);
});

test('origin forms of the same GitHub repo normalise alike', async () => {
  const { normalizeOriginUrl } = await import('./projectIdentity.js');
  const forms = ['https://github.com/quodeq/quodeq.git', 'https://github.com/quodeq/quodeq/', 'git@github.com:quodeq/quodeq.git', 'ssh://git@github.com/quodeq/quodeq', 'https://token@github.com/quodeq/quodeq'];
  for (const f of forms) assert.equal(normalizeOriginUrl(f), 'github.com/quodeq/quodeq');
  assert.equal(normalizeOriginUrl(null), null);
  assert.equal(normalizeOriginUrl('  '), null);
});

test('a run is filed under the project with the same origin', async () => {
  const { findProjectByOrigin } = await import('./projectIdentity.js');
  const projects = [{ id: 'p1', name: 'quodeq', originUrl: 'git@github.com:quodeq/quodeq.git' }, { id: 'p2', name: 'other', originUrl: null }];
  assert.equal(findProjectByOrigin(projects, 'https://github.com/quodeq/quodeq')?.id, 'p1');
  assert.equal(findProjectByOrigin(projects, null), null);
  assert.equal(findProjectByOrigin(projects, 'https://github.com/x/y'), null);
  assert.equal(findProjectByOrigin(null, 'https://github.com/quodeq/quodeq'), null);
});
